/**
 * ExecutorProxy - stable reference that forwards executeScript calls to a
 * swappable inner executor, gated on a readiness promise.
 *
 * Solves the launcher-swap race: when persistent-mode auto-launch resolves
 * mid-call and the tool handler had already captured a `let executor`
 * binding, the rest of the in-flight call would either still use the old
 * executor (closure-binding semantics in JS reads lazily, but the result is
 * the same: no atomic swap point), or two parallel calls that arrive within
 * the swap window would land on different executors and race on the same
 * project file.
 *
 * The proxy reference is stable (`const`), and every executeScript awaits
 * the readyPromise first. swap() updates the readyPromise; new calls block
 * on the new promise until it resolves, then run on the new inner executor.
 * Calls that started before swap() finish on whichever inner they snapshotted.
 */
import { IpcResult, ScriptExecutor } from './types';

export class ExecutorProxy implements ScriptExecutor {
  private inner: ScriptExecutor;
  private readyPromise: Promise<void> = Promise.resolve();
  // Monotonic version stamp - each swap call increments it, and pending
  // chains compare against the live version before applying their inner.
  // Stops a slow-resolving background swap from later overwriting a faster
  // explicit swapNow (e.g. user calls launch_codesys while the auto-launch
  // is still resolving).
  private swapVersion: number = 0;

  constructor(initial: ScriptExecutor) {
    this.inner = initial;
  }

  /** Replace the inner executor once `newReady` resolves.
   *
   * Calls to executeScript that arrive AFTER this returns will block on
   * newReady before delegating to the new inner. If newReady rejects, the
   * old inner stays in place and subsequent calls run on it.
   */
  swap(newInner: ScriptExecutor, newReady: Promise<void>): void {
    const myVersion = ++this.swapVersion;
    // Chain the new readiness onto whatever was previously pending so callers
    // never see the inner change without a corresponding readyPromise resolve.
    const chained = this.readyPromise.then(() => newReady);
    this.readyPromise = chained;
    chained
      .then(() => {
        if (myVersion === this.swapVersion) {
          this.inner = newInner;
        }
        // else: a later swap superseded us; do nothing.
      })
      .catch(() => {
        if (myVersion === this.swapVersion) {
          // Keep the old inner. Reset readyPromise so future calls don't block.
          this.readyPromise = Promise.resolve();
        }
      });
  }

  /** Synchronously swap the inner executor with no readiness gate. Use only
   *  for explicit tool-driven transitions (launch_codesys, shutdown_codesys)
   *  where the caller has already awaited the underlying readiness.
   *  Bumps swapVersion so any pending background swap won't overwrite us. */
  swapNow(newInner: ScriptExecutor): void {
    this.swapVersion++;
    this.inner = newInner;
    this.readyPromise = Promise.resolve();
  }

  /** Snapshot the current inner reference - useful for status reporting. */
  current(): ScriptExecutor {
    return this.inner;
  }

  /** 一次性惰性启动器槽位。第一次 executeScript 被调用时消费，之后置空。
   *  用途：MCP 服务器连接时不拉起 InoProShop，只有真正有工具调用时才启动，
   *  避免「打开 WorkBuddy / 启用 MCP 就弹 IDE 窗口」。 */
  private lazyStarter: (() => Promise<void>) | null = null;

  /** 注册一次性惰性启动器。starter 由调用方负责把 executor 切到 persistent
   *  （内部调用 swapNow），本方法只做「第一次调用时触发一次」。 */
  armLazy(starter: () => Promise<void>): void {
    this.lazyStarter = starter;
  }

  async executeScript(content: string, timeoutMs?: number): Promise<IpcResult> {
    // 惰性启动：第一次调用时 kick 一次并等待完成。抛错则吞掉、保持当前 inner
    // （HeadlessExecutor）继续执行 —— 等价于 fallback-headless。
    if (this.lazyStarter) {
      const s = this.lazyStarter;
      this.lazyStarter = null;
      try {
        await s();
      } catch {
        // 启动失败：不再重试（避免每次调用都卡满 ready-timeout），继续 headless。
      }
    }
    await this.readyPromise;
    return this.inner.executeScript(content, timeoutMs);
  }
}

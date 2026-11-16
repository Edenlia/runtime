# System.Native.Browser 指针入口 ABI

本次修复只有生产 `libSystem.Native.Browser.footer.js` 的两条 Emscripten 签名：

- `SystemJS_RandomBytes`: `ipi`，对应 `int32_t(uint8_t*, int32_t)`。
- `SystemJS_GetLocaleInfo`: `ppipipip`，对应四个指针参数、三个 int32 参数和一个指针返回值。

MEMORY64=1 与 MEMORY64=2 都保留 i64 的 C 指针参数；lowering 并不把此 ABI 改成 i32。原始生产 Rollup 库把 BigInt 直接传给使用 Number heap offset 的实现，随机数的位移和 locale 的地址运算发生 TypeError。`__sig` 让 Emscripten 在真正的 import 边界转换指针入参，并将 locale 的 Number 指针结果转回 native i64。算法及其 32 位路径没有变化。

验证使用实际 Release Rollup 导出的 Browser 和 Utils 库、C 调用者以及正式 Emscripten 6.0.10 linker；没有手写 JS 替换被测函数。生产库输入 hash、完整命令、工具链来源、原始结果和最终 import 签名见同名 [JSON](2026-11-17-system-native-browser-abi.json)。独立 C/JS fixture 只放在该记录声明的 artifact store，不恢复仓库专项测试框架。

| Lane | 结果 |
|---|---|
| wasm32，默认 BigInt | 原始与候选五场景均通过 |
| 原生 wasm64 | 原始四个指针入口场景失败；候选五场景通过 |
| wasm64，MEMORY64=2 | 原始四个指针入口场景失败；候选五场景通过 |
| MEMORY64=2 + pthread/WasmFS | 原始四个指针入口场景失败；候选五场景通过 |
| wasm32，WASM_BIGINT=0 | 前后均有既有 `$HEAP64` 链接失败；未记作 PASS |
| Chrome 157.0.8103.52，lowered64 + pthread/WasmFS | 五场景通过，均 exit0，无 page/console errors |

五场景为 70,002 字节分批随机数与空输入、英文 locale、中文 locale、真实 UTF16 错误字符串分配/返回及 Unicode UTF8 分配。Node 共 20 项通过；Chrome 另有五项。Chrome 运行于 COOP/COEP 的实际 shared heap，确认生产随机数代码把 65536/4466 字节两批复制到非 shared buffer 后调用真正 WebCrypto；另一个 shared buffer 负控被 Chrome 明确拒绝。该记录不是只有 Node 的替代结果。

实际产物也证实原有 Utils `_malloc` 已经由 Emscripten 的 `makeWrapper_pp` 适配，原始 64 位 UTF8 分配本来就通过。因此没有增加分配器封装、修改共享 ambient 或改写 Utils。所有成功的最终 JS（包括 Chrome 产物）均无运行时 `new Function`、`eval(` 或未展开 Emscripten macro；修改文件 ESLint 通过，两种宽度 Rollup 均正常 exit0。

范围仅是小于 4 GiB 地址的实际 ABI 类型转换。crypto/string helpers 既有 `>>>0` 地址截断没有改变，也没有观测高地址堆。本次没有链接或执行 CoreCLR，不证明 managed 初始化、GC/finalizer、完整 loader、UE 打包或 Wasm 游戏已经可用。

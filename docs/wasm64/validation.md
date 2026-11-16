# 验证记录与证据边界

## 当前实现与历史运行的关系

A/B/C/D 原先已执行验证，随后按用户要求删除新增非矩阵测试并 amend。
生产代码 blobs 保持不变，但提交 SHA 改变。历史 receipts 保留原始 SHA，不改成“新 SHA 已重跑”。
`evidence/history-rewrite.json` 和 `evidence/independent-final-audit.json` 记录该对应关系。
B 删除专项测试后实际重编译并运行既有 128 项，全部通过，0 skip。
初始 eden-main checkpoint 只增加文档/JSON，没有重新构建或执行 guest。

## 后续 browser host 指针槽修复

2026-11-16 在 `49331864275` 上采用历史提交
`32897fcda86e6dce91d2812c0686cd3adc2bfcdd` 的六个生产文件。
当前 CoreCLR 路径是 `src/native/rollup.config.js` 生成的 `libBrowserHost.js`，
由 `BrowserWasmApp.CoreCLR.targets` 与 `libBrowserHost.a` 一起链接；其入口是
`src/native/libs/Common/JavaScript/host/index.ts`，并非据旧 Mono startup 文件推定。

- 原始 checkpoint 在 8-byte property 指针槽检查中失败，截断后无法恢复属性。
- 修复后本地 JavaScript host 检查 49 项通过：wasm32 Number、wasm64 Number、
  wasm64 BigInt；包含 property/argv、普通 DLL/PDB/ICU slots、probe 清零、
  memory view 替换、无效数值拒绝及大于 4 GiB 的指针**值**。
- 正常 Release Rollup 在 `WasmPointerSize=4` 和 `8` 下各完成八份 JS/type 输出，
  修改文件的 ESLint 和 `git diff --check` 通过。
- 检查使用模拟 native host；没有执行 CLR guest、真实 native callback、浏览器，
  也没有访问大于 4 GiB 的 heap 地址。没有因此改变下列执行 gate 的 NOT RUN。
- `MEMORY64=2` 是 UE 5.9 默认链接的独立兼容性需求；本修复按 C/C++ ABI 的
  8-byte slots 处理 Number/BigInt 输入，但没有建立 runtime 与 UE 链接兼容性。
  WebCIL memory/table globals、corerun、完整 JS interop 与 SDK/runner 接线仍待完成。

命令、输入、输出哈希及 artifact 路径见
[机器可读记录](evidence/2026-11-16-browser-host-pointer-slots.json)。

## corerun external-assembly 原生边界

以 `f8d91aa99e45eef02b748764ef418df52b4b4541` 为 base，修复
`libCorerun.js` 的 `ippp` callback signature、原生 allocator 参数、临时/输出
指针槽和 `int64_t` size。Emscripten 的 `toIndexType` 与 `MEMORY64 == 1` 决定
最终 memory/table 的 JS API 类型；`MEMORY64=2` 仍使用 8-byte C ABI，
最终 memory/table globals 使用 i32。wasm64 R2R 在 probe 中明确拒绝，未扩大其支持范围。

精确 Emscripten 6.0.10（`d6c521a7f05449857c76bd99e396895583cf2083`）、
Node 24.19.0 已实际编译并执行原始 `libCorerun.js` 加 C stub：

| Lane | Base | 修复后 |
| --- | --- | --- |
| wasm32，`WASM_BIGINT=0` | PASS | PASS |
| wasm32，默认 BigInt | PASS | PASS |
| `-m64` 原生 Memory64/table64 | FAIL：UTF8ToString 收到 BigInt | PASS |
| `-m64 -sMEMORY64=2` | 同上 | PASS |

修复后检查真实 C/JS callback、已 poison 的输出指针全部字节、64-bit size、
payload bytes、missing image，以及 wasm32 table-bearing fixture 的原协议路径和
两种 wasm64 的 R2R 拒绝诊断。fixture 是最小 self-installing version-2 协议模块，
payload 仅四个已知字节；不是 CLR image，也没有执行托管方法。
原生 Memory64 fixture 专门匹配当前 probe 的 memory64 import，不代表现有
`WebcilWasmWrapper` 已能输出它。没有高地址 heap、GC 或完整 runtime 产品验证。

命令、来源和原始日志见
[corerun probe 记录](evidence/2026-11-16-corerun-pointer-probe.json)。

## 共享 browser host 的原生调用与 callback

以 `b803f30270f1fbcbc6b048a0b50b77946cb130d2` 为 base，增加一个由
Emscripten `to64/from64Expr` 生成的 `browserHostNative` adapter，供 TS host
统一调用 allocator 和 BrowserHost/ICU 原生入口。callback 通过稳定 `ippp`
wrapper 委托当前 module exports，不再在初始化时覆盖编译器生成的转换。
这些函数在 Rollup minify 后、Emscripten link 时生成，最终 runtime 函数没有宏或
额外动态编译；未改变 runtime 的 SDK pin。

普通 Release Rollup 在 pointer size 4/8 下各生成八份输出；实际将 minified
`libBrowserHost.js` 与 C host stub 链接，并以 Emscripten 6.0.10 / Node 24.19.0 执行：

| Lane | 修复前 | 修复后 |
| --- | --- | --- |
| wasm32 early attachment，对照 | PASS | PASS |
| wasm32 deferred attachment，BigInt on/off | FAIL：仍调用 dummy import | PASS |
| native wasm64 / `MEMORY64=2` | FAIL：原生入口收到 Number | PASS |
| native wasm64，无 ICU symbol | 同上 | PASS；未引入 ICU link dependency |

覆盖 property arrays/RID/host contract、Unicode argv/null terminator、DLL/PDB/ICU
slots、真实 native callback、missing image 清零。另检查 forced allocator failure
恢复 stack、真实 native invalid-alignment 返回值，以及 malformed module 失败后
通过 adapter 释放 payload。没有声称解决既有 host 的全部资源生命周期问题。

官方 Emscripten tag 6.0.2 的 `parseTools.mjs/jsifier.mjs` 源码也确认所用
pointer macros 和 `ippp` 转换存在；这是源码兼容性检查，未执行 6.0.2 二进制。
完整来源、bundle hashes、六个 lane 与限制见
[native boundary 记录](evidence/2026-11-16-browser-host-native-boundary.json)。
这些检查仍是 C stub，没有链接 CoreCLR、执行托管方法、浏览器或高地址 heap；
完整 loader/WebCIL/JS interop gate 保持 NOT RUN。

## Browser PAL ABI

`67e37f25af2` 仅增加 RandomBytes 与 GetLocaleInfo 的 Emscripten 原生指针
签名。原始 64 位生产 bundle 的四个指针入口场景失败，候选在 wasm32、
native64、lowered64、lowered64 + pthread/WasmFS 四条 Node lane 共 20 项通过。
Chrome 157 的真实 shared heap 另有五项通过，包括真正 WebCrypto 分批随机数与
shared-buffer 拒绝负控。wasm32 + WASM_BIGINT=0 的既有 HEAP64 链接失败仍未解决，
不列为 PASS。没有执行 CoreCLR，也没有观测高地址。
详见 [独立记录](evidence/2026-11-17-system-native-browser-abi.md)。

## 生产 IL WebCIL Memory64

本次使用实际生产转换器处理真实 managed IL 和 matching wasm64 CoreLib，
不把手写 protocol fixture 作为生产者。普通 task build 无 warning/error，
现有 WebcilInWasmSizesTests 类的 32 项通过；SDK 真实配置与 build 转换 target
的八次调用验证 Mono/CoreCLR 默认值、精确 RID 回退、显式 lowering，以及
false → true → true（保持输出时间戳）→ false 的增量行为。

生产 wrapper 在 wasm32、native64 和 lowered64 的 Node 24 / Chrome 157
运行中均通过，每条 lane 包含两份 assembly 的 buffered/streaming 四次加载。
检查实际 memory/base imports、getWebcilSize 的完整四字节值、16-byte
allocation 对齐、native memory bounds 与逐字节 payload、8-byte callback
指针槽、真实 table.grow 的 Number/BigInt 边界，以及错误 profile 的 LinkError、
单次释放和不注册。Mono v0 与 CoreCLR v1 对两份真实输入的默认输出，都与
另行构建的未修改 baseline 生产转换器逐字节一致。

公开 `WasmWebcilMemory64` 描述最终 imports，不代表 C ABI。lowered64 必须
显式 false；独立的 TargetArchitecture guard 保证这仍不能采用 wasm32
prebuilt R2R。build/publish stamps 与 per-file profile 检查均包含该选择。
这些是 unshared wrapper/native C stub 的真实执行，未链接 CoreCLR；
shared-memory wrapper、完整 SDK publish dispatch 与 wasm64 R2R 仍不支持。
见 [合同](webcil-memory64.md) 与 [receipt](evidence/2026-11-17-webcil-memory64.json)。

## A/B/C/D 历史构建记录

| Lane | 实际被测提交 | 实际结果 | 当前解释 |
| --- | --- | --- | --- |
| A CoreLib | `4175b10e2b2bdc5e3e8e4759e10d10aaad6bf628` | wasm32/64 × Release/Checked 四份真实 CoreLib；属性与 IntPtr/UIntPtr IL 宽度检查通过 | 当前 A `5da8cf7` 产品代码相同；新增验证 harness 已移除 |
| B generation | `148a4065a580b7384103764803ecf237fbfd30bd` | 普通 Crossgen2 build、154 host cases、13 generation cases 通过 | 其中26专项 cases已删；64输入为外部真实A CoreLib，framework/host ELF为显式历史fixture |
| B 既有 suite | amend前、与当前 `be6740d` 一致的最终源码 | `WasmArgumentLayoutTests` 128 passed / 0 failed / 0 skipped | 本轮删除测试后的真实重编译结果，不新增 case |
| C dependency | `af73b3b96cf3ddcbcb33f8220ca8b09c554bd454` | 22项历史检查、7 syslibs冷构建1340成员、ICU441成员检查及API probe通过 | 当前 C `02c0d1c` 三生产文件一致；本lane没有重新从源码完整编译ICU，使用有来源的既有archives |
| D native Release | `291ce28441f725fbd020cdea78ebd8eea2237a3b` | 全新 clr.runtime+clr.hosts，636 tasks，8m58.52s，0 warning/error；产物检查通过 | 当前 D `259251b` 生产代码相同；此新构建仅Release，不声称新的Checked/guest/独立libs.native publication通过 |
| D actual ASM control | 同上 | stock SDK expected failure：expected i32 / got i64；用户8620 MC成功，type-check开启 | stock失败是已知工具链阻塞的复现，不是完整stock构建PASS |
| D module/archives | 同上 | 2 runtime archives/397成员；14个interp+side+sysroot输入/1411成员；17 kit archives/1039成员；Memory64/table64，Node Module和wasm-opt通过 | Node未instantiate/execute CoreCLR guest；最大内存8GiB不等于实际高地址访问 |
| amend/发布 | 当前四tips | 生产blob核对、原suite/helper/CI恢复、无悬空引用、分支拓扑与远端核对通过 | 只更新目标四refs，未额外追加功能commit |

## LLVM provenance

- stock LLVM base：`b7cbe9c6cf3ea97cc5822cf324cbcef06f54a397`。
- 用户修复：[8620eb7b55e857a5f6e430be624b5a6605e8c53e](https://github.com/Edenlia/llvm-project/commit/8620eb7b55e857a5f6e430be624b5a6605e8c53e)。
- 原样 backport 到 pinned base 后构建独立 MC，SHA256 `acfd06dbd88edabf65ba37181769d92c76dccfa6e9701e9e2724a4e5a5775025`。
- D 的 C/C++/link 使用 stock SDK，`.S` 通过外部实验 adapter 使用该 MC；类型检查未关闭。
- receipts 里的 source repo 是 base对象来源；tested-source snapshot和补丁/二进制哈希用于标识实际测试组件。不能把恢复了旧实验 patch 的工作树冒称用户修复源码。
- 上述历史 D 只使用独立 MC，没有构建完整 fixed Clang/SDK，也没有证明所有 table64 instructions 均被修复。

### 本轮普通 Clang 工具链

2026-11-17 的新验收使用精确 Emscripten 6.0.10：
LLVM `a06d9165905ce89b5ffef2bbb84c886d60a9b8bf` 加用户
`8620eb7b55e857a5f6e430be624b5a6605e8c53e` 的原样 checker patch，
构建普通 Release/assertions-on Clang 与 llvm-mc；实际 Clang SHA256
`6c5ce14d830a38be10991a4d639a881b32d6399e3d59717cf8f9d3ce732590a4`。
通过 process-local `EM_LLVM_ROOT` 选择独立 overlay，保留可追溯的 stock
linker/sysroot 与其它工具，不覆盖原 SDK binaries，不使用外部 MC adapter 或
type-check suppression。

正常 driver 的 integrated assembler 在 wasm32/wasm64 的 named/default-zero
table 形式接受四个正确输入、拒绝四个错误宽度输入；compiler-generated C →
assembly → object → module 的 wasm32/native64/lowered64 三条 lane 真实执行通过。
另有 pthread/WasmFS 的 C/JS data/function-pointer ABI smoke 通过。
原始记录保持在 task artifact store 的 `UE/FixedProbe` 与
`Toolchain/fixed-llvm/provenance.json`，不被本次 WebCIL 记录覆盖；
其工具链身份也列于 [WebCIL receipt](evidence/2026-11-17-webcil-memory64.json)。
仓库 pin 6.0.2 未变，未声称该 pin 的二进制矩阵或所有 table64 指令均已验收。

## 可使用的产品入口

```sh
# 仅需 checkout pinned dotnet SDK；不依赖 LLVM
./build.sh -os browser -arch wasm64 -c Release -subset clr.corelib
./build.sh -os browser -arch wasm64 -c Checked -subset clr.corelib
# wasm32 对照
./build.sh -os browser -arch wasm -c Release -subset clr.corelib
./build.sh -os browser -arch wasm -c Checked -subset clr.corelib
```

完整 native runtime 的产品命令、依赖及 helper regeneration 见
[build bring-up](../design/features/wasm64-bringup.md)、[ICU](../../eng/wasm/README-memory64-icu.md)、[helper generator](../../src/coreclr/vm/wasm/generate-coreclr-helpers.md)。
stock pinned SDK 缺 table64 修复，不能预期完整 native 命令直接成功。历史 adapter不作为本次新增脚本放回分支。

## 尚未验收

CoreCLR guest execution、guest 内真实 native 双向调用、GC/EH/异步恢复、高地址/growth/live-set、链接 CoreCLR 的 browser host/IL WebCIL、完整 JS interop、真实 R2R 方法执行和安装 workload 后的应用运行均未在当前 checkpoint 验收。上述真实 producer/loader 与 PAL native-stub 检查不代替这些 guest 验收。
原始完整计划中的全部 baseline lanes也不能由局部native/host记录推定完成。

## 后续运行摘要模板

```json
{
  "checkpoint": "<exact source SHA>",
  "source_dirty": false,
  "lane": "<existing suite/matrix and configuration>",
  "result": "NOT RUN",
  "base_sha": "<base>",
  "toolchain_revisions": {},
  "commands": [],
  "input_artifact_hashes": {},
  "counts": {"executed": 0, "passed": 0, "failed": 0, "skipped": 0},
  "native_calls_executed": false,
  "guest_executed": false,
  "compiled_body_observed": false,
  "high_address_observed": null,
  "raw_artifacts": [],
  "limitations": []
}
```

模板不是已执行结果。zero tests、全skip、CLI help、只看文件名、只有Module验证均不能代替功能PASS。按原计划§13记录seed/iterations/内存峰值、输入来源及实际读写证据。

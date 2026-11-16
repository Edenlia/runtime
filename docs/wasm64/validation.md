# 验证记录与证据边界

## 当前实现与历史运行的关系

A/B/C/D 原先已执行验证，随后按用户要求删除新增非矩阵测试并 amend。
生产代码 blobs 保持不变，但提交 SHA 改变。历史 receipts 保留原始 SHA，不改成“新 SHA 已重跑”。
`evidence/history-rewrite.json` 和 `evidence/independent-final-audit.json` 记录该对应关系。
B 删除专项测试后实际重编译并运行既有 128 项，全部通过，0 skip。
本次 eden-main 只增加文档/JSON，不改变产品树，也没有重新构建或执行 guest。

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
- 当前没有构建完整 fixed Clang/SDK，没有证明所有 table64 instructions 均被修复。

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

CoreCLR guest execution、真实 native双向调用、GC/EH/异步恢复、高地址/growth/live-set、normal browser host/IL WebCIL、完整JS interop、真实R2R方法执行和安装workload后的应用运行均未在当前checkpoint验收。
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

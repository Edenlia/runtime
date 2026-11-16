# CoreCLR wasm64 整体进度入口

本目录随 `wasm64/eden-main` 维护完整实施计划、决策、分支关系、验证记录与下一步任务。
记录日期：2026-11-16。原生构建 checkpoint：`259251bb79268a221f0019edd1ad9d384fa1a3c3`。
本分支直接继承 D，因此已包含 type-system 与 A/B/C/D 的全部当前实现。
当前成果是 target/layout/native build checkpoint，整个 wasm64 port 尚未完成。

独立前置分支 `test/eden-web-build-host` 的 Windows 路由、MSYS2 ICU 与显式工具链环境见
[Windows build-host prerequisite](windows-build-host.md)。该记录分别标明配置、托管构建、
依赖与真实 guest 的执行状态，不改变本分支的默认 SDK pin。

后续最小修复已恢复 CoreCLR browser host 的指针宽度传递、property/argv 与普通
DLL/PDB/ICU 指针槽。它来自历史提交 `32897fcda86e6dce91d2812c0686cd3adc2bfcdd`，
已重新执行 wasm32/wasm64 JavaScript host 检查与两个宽度的 Release Rollup；
这不表示已经执行 CoreCLR guest、高地址内存或完整 browser loader。
具体证据见 [browser host pointer slots](evidence/2026-11-16-browser-host-pointer-slots.json)。

随后补齐共享 browser host 的 JS/native 调用 adapter 与稳定 `ippp` callback：
同一份 minified `libBrowserHost.js` 已在真实 C host stub 下通过 wasm32、原生/降级
wasm64 和无 ICU linkage 检查，包含失败后的 stack/payload 清理；
仍未链接 CoreCLR。见 [browser host native boundary](evidence/2026-11-16-browser-host-native-boundary.json)。

corerun 的 external-assembly probe 也已改用 Emscripten 的原生指针 signature、
slot/call/index 宏，并区分原生 Memory64 与 `MEMORY64=2` 的最终 globals。
在精确 Emscripten 6.0.10 上，四种 C/JS 原生 stub lane 已执行通过；
这使用最小 WebCIL protocol fixture，尚未执行 CoreCLR guest 或真实 managed image。
wasm64 R2R image 仍明确拒绝。见
[corerun probe](evidence/2026-11-16-corerun-pointer-probe.json)。

## 阅读顺序

1. [原始完整计划](plan/original-cloud-implementation-plan.md)：用户上传文件的逐字节存档，包含所有工作单、命令候选、阶段 gate 和完成标准。
2. [当前决策与计划调整](decisions.md)：解释原始计划中哪些提议已被后续讨论替代。
3. [完整路线与任务状态](roadmap.md)：原计划九个功能方向、SDK 配套方向及阶段验收状态。
4. [分支与执行流程](workflow.md)：review 边界、依赖、集成与交接方式。
5. [验证记录与限制](validation.md)：历史运行与当前源码的对应关系；编译、模块验证和 guest execution 分别记录。
6. [机器可读状态](status.json)：分支 SHA、状态、阻塞及下一步。
7. [证据目录](evidence/README.md)：已归档的原始结果摘要、生产者记录及校验清单。
8. [现有布局/构建设计](../design/features/wasm64-bringup.md)：当前代码的具体合同与构建接口。

## 当前分支

| 范围 | Review branch | 当前提交 | 状态 |
| --- | --- | --- | --- |
| 类型系统与命令行 | `wasm64/type-system` | `72d457a4c6a192e5f46be3f37ca7a9737cc7146a` | 已实现；关联上游 PR #137612，不据此宣称已合并 |
| A：目标选择 / IL CoreLib | `wasm64/01-target-corelib` | `5da8cf731c431605cf3b73d81418673030dc871a` | 已实现，待分项 review |
| B：host tools / portable helpers | `wasm64/02-portable-helpers` | `be6740da5da33c732a58ca968020a8d208cd49c4` | 已实现，原有 128 项测试通过 |
| C：memory64 依赖 | `wasm64/03-memory64-dependencies` | `02c0d1c46e1251c07fa918b1b7002e3ed05699ca` | 已实现，原 SDK 路径已验证 |
| D：native runtime 集成 | `wasm64/04-native-integration` | `259251bb79268a221f0019edd1ad9d384fa1a3c3` | 已实现；完整构建需要修复 table64 检查的 assembler |
| 整体集成与记录 | `wasm64/eden-main` | 代码基于上述 D；记录提交以 Git 为准 | 当前长期跟踪入口，不作为累积大 PR 提交 |

本目录是项目记录，不增加测试框架、执行脚本或 CI。原始文档中给执行者的命令是历史方案文本，不能当作本分支已经支持或已经执行的事实。以后修改代码与状态时，应同时更新对应记录。

关联讨论：[runtime #94108](https://github.com/dotnet/runtime/issues/94108)、[计划评论](https://github.com/dotnet/runtime/issues/94108#issuecomment-6888585388)、[type-system PR #137612](https://github.com/dotnet/runtime/pull/137612)。

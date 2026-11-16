# 已确认决策与原始计划的调整

原始上传计划保持原样。下列记录反映之后的用户决定，阅读原计划时应一起参考；未记录的方案仍需根据实际源码和实验确认。

| 编号 | 当前决定 | 对原始计划的影响 |
| --- | --- | --- |
| D01 | 使用 native Memory64、browser、CoreCLR、初始单 managed thread | WASI、Mono wasm64、NativeAOT、managed 多线程和 compatibility lowering 不属于当前支持范围 |
| D02 | 独立 helper-only/bootstrap DLL 不是强前置，不实施为必需功能 | 替代原计划 §3、§6、§7.1、§11 中要求独立 bootstrap 路径的表述。使用标准 Crossgen2 的已有 portable generation 入口；只有真实可复现构建阻碍才讨论最小依赖解耦 |
| D03 | 基础工作按 A/B/C/D 审查；A/B/C 独立，D 汇合三者 | 替代最初把 foundation 当成一个大 PR 的组织方式。原九个功能方向继续用于完整路线管理，不预先限定 PR 数量 |
| D04 | 移除 A–D 所有非既有矩阵扩展的新增专项测试 | 已删除新增 Python/MSBuild/C# harness、native probe tests、新专项 xUnit 类和仅供其使用的 fixture、专项 CI 与引用；原有矩阵和产品构建校验保留。不得通过计划归档恢复这些测试 |
| D05 | 只用真实匹配目标的 CoreLib、framework 与 native 依赖 | B 的 64 位生成验证曾显式消费 A 的 CoreLib，属于输入依赖，不是 B 引入 A 源码。原始框架/host ELF fixture 的来源见历史 receipts |
| D06 | LLVM 问题在工具链解决，产品中不加入类型检查绕过 | 用户修复 `8620eb7b55e857a5f6e430be624b5a6605e8c53e`。A/B/C 不依赖修复；D 当前 `.S` table64 路径需要正确检查器 |
| D07 | 区分普通 SDK、修复 MC 实验和整套 fixed Clang | 已验证的是 stock C/C++/linker + 用户补丁原样 backport 的 llvm-mc；全 fixed Clang/SDK 尚未构建。不能把组件验证写成完整 SDK 验证 |
| D08 | `wasm64/eden-main` 作为整体跟踪与集成入口 | 本次从 D 新建；旧 `wasm64/integration`、旧实验分支及 backup 分支不因此更新或认定完成 |
| D09 | review 分支只承载对应产品变更，整体跟踪文档留在 eden-main | 后续按必要依赖拆 PR；不将整条集成历史一次提交上游。用户未授权时不发送评论或创建 PR |

`Wasm64Validation.targets`、CoreLib Platform guard、编译器宽度检查、ICU/sysroot 架构核验及 native static_assert 属于产品构建正确性，不是被删除的专项测试。

原始计划要求的 ABI、高地址、浏览器、GC/EH、R2R 等正确性目标仍然存在。测试实现优先扩展现有通用套件/矩阵；新增架构专用框架不作为默认实施方案。是否需要新框架应另行说明理由并由用户决定。

开发 RID `browser-wasm64` 是 in-tree 身份，尚不代表正式 workload/RID graph 承诺。`Architecture.Wasm` 仍是公共 Wasm family 身份。当前拒绝未实现的 wasm64 完整 JIT/R2R 编译。

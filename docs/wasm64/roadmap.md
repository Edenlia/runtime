# 完整路线与验收任务

状态：`IMPLEMENTED` 表示相关代码已实现；`PARTIAL` 表示仅部分交付；`NOT STARTED` 表示未在当前 checkpoint 交付。代码状态与验收状态分别记录。运行结果仅使用 PASS / FAIL / BLOCKED / NOT RUN / NOT APPLICABLE。所有完成标记必须附实际 source SHA 和证据。

## 原计划方向映射

| 原计划章节/方向 | 当前交付 | 尚需完成 | 整体验收 |
| --- | --- | --- | --- |
| §5、§8 环境和 wasm32 baseline | 有源码/工具链记录、wasm32 产品与 host 测试基线 | 原计划完整 browser/SDK baseline 不能凭这些记录算通过 | PARTIAL |
| §7.1 target-foundation | type-system + A/B/C/D：目标、宽度/布局、CoreLib、helpers、ICU/sysroot、native build、产物隔离 | target-aware runtime runner、完整 CORE_ROOT/pack/browser 接线、干净环境重现、完整 fixed SDK 验证 | PARTIAL |
| §7.2 managed-abi | B 的 calling convention/helper producer 与 D 的 native layout/consumer 编译集成 | 真正解释器执行、双向 ABI、aggregate/retbuf/byref、callback-GC、EH/stackwalk、真实 suspend/resume 经 GC | PARTIAL；执行 NOT RUN |
| §7.3 gc-memory | D 有指针宽度、barrier 与 Wasm segment 默认策略改动 | collection、growth、reservation/accounting、allocation failure、真实高地址 roots/interior refs/pinning、压力实测 | PARTIAL；执行 NOT RUN |
| §7.4 browser-loader | 当前 corerun native 模块可构建/验证 | normal host、argv/properties、普通 DLL 与 IL-only WebCIL、asset manifest、Chrome 真运行、GC/EH/native 联合验收 | NOT STARTED |
| §7.5 js-interop | 未交付完整 shared JS ABI | managed/TS 布局、Number/BigInt/range checks、imports/exports、strings/spans/arrays/promises、growth 后 views、相关 Mono wasm32 回归 | NOT STARTED |
| §7.6 jit-codegen | 保留明确不支持诊断；portable generation 可用 | wasm64 JIT/emitter、address relocations、writer/stubs、可验证最小编译模块 | NOT STARTED |
| §7.7 r2r-modules | 未交付执行支持 | module loader/fixups、双向 mixed transitions、partial/composite/fallback、compiled-body 证据与 R2R=0 对照 | NOT STARTED |
| §7.8 sdk-publish | 有本地目标路径隔离 | packs/RID graph/manifests、compiler resolver 镜像、新测试 SDK、workload 安装及 build/publish/relink/run | NOT STARTED |
| §7.8 dotnet/sdk 配套 | 未修改 SDK 仓库 | target/compiler/pack resolution 与已有 SDK 测试矩阵扩展，单独记录 SDK SHA | NOT STARTED |
| §7.9 ci-coverage | 保留既有 CI/矩阵；新增专项 gate 已按要求删除 | 随已支持能力扩既有 matrix，配置 pin、高内存窗口、适用诊断与性能/内存基线 | NOT STARTED |

## G0 — 环境与对照

- [x] 固定 runtime 原始基线 `2b5ea9af2991abe307beb855729ab52409d6333f` 与当前共同基线 `72d457a`。
- [x] 记录 SDK label 6.0.2 与实际 emcc 6.0.3 / Clang 23.1.0 差异。
- [x] 有 wasm32 CoreLib、普通 host compiler 和 native 构建对照记录。
- [ ] 完成原计划 §8 全部 browser/SDK baseline，并逐项记录失败/阻塞。
- [ ] 在干净环境重复当前 wasm64 checkpoint；本机历史缓存不能代替 clean-room 复现。

## G1 — Target 与 ABI 接口

- [x] Wasm64 type-system data layout 与命令行识别，沿用已有通用布局矩阵。
- [x] A：显式目标不被 browser 默认覆盖；CoreLib 采用 64 位条件；错误组合拒绝。
- [x] B：标准 Crossgen2 portable generation 使用 guest 宽度，生成输出按目标隔离。
- [x] C：ICU 构建/校验和原 SDK sysroot 路径；D 接入产品构建。
- [x] D：native Memory64、table64、runtime/依赖/kit 产物及模块验证（历史 Release lane）。
- [ ] 完整 fixed Clang/SDK 的正常驱动构建，不依赖实验性的外部 MC adapter。
- [ ] runtime runner、最小解释器 guest 和真实双向 native ABI 验收。
- [ ] 当前 review base/head 对应的必要 wasm32/wasm64 回归重跑，取得上游 review。

G1 的 build 部分有证据；完整 ABI 接口 gate 尚未满足。独立 helper-bootstrap 不列为 gate。

## G2 — 普通浏览器解释器闭环（首个完整目标）

- [ ] 修通 arithmetic/object/array/generic/interface/delegate/EH 的解释执行，显式 interpreter-only。
- [ ] 真正双向调用，覆盖 pointer/nint 与普通 i64 的区别、native 读写、struct/retbuf/ref/out、合法 callback-GC。
- [ ] 真实异步 suspension，至少一个 continuation 暂停时经过 GC 后恢复。
- [ ] normal host + manifest + Chrome，分别通过普通 DLL 和 IL-only WebCIL 资产路径。
- [ ] argv、Unicode、environment、退出结果和 `IntPtr.Size == 8`。
- [ ] 高地址正确性：实际地址大于 `0xffffffff`，读写、pointer round-trip 和别名负例。
- [ ] managed 高地址对象/roots/interior refs/pinned buffers 经 collection 后正确。
- [ ] growth/GC 压力与大 live-set/limit job 分开运行，记录 seed、iterations、实际触达字节、RSS/峰值和定义好的失败。

不能以 Node Module 验证、最大内存为 8 GiB 或单个大整数代替上述执行证据。

## G3 — JS 与 compiled execution

- [ ] managed/TS shared marshaling layout 同步，所有指针路径不截断，handle/flag 语义保留。
- [ ] 真实 JS imports/exports、numeric/string/array/span/delegate/promise/exception/lifetime。
- [ ] growth 后刷新视图；真实高地址 buffers 与 safe-integer 数值边界分别验收。
- [ ] 最小 wasm64 编译模块通过 validator；relocation 边界/溢出有适用的通用测试。
- [ ] runtime 真正消费 R2R，记录方法级 compiled-body 命中；R2R=0 对照证据消失。
- [ ] interpreted/compiled/native 双向 transitions、partial/composite/fallback、GC/EH/async。

## G4 — 发布、回归与长期维护

- [ ] runtime packs 与 dotnet/sdk resolver/测试配套，固定两个仓库的 SHA。
- [ ] 从新包安装测试 SDK/workload；clean restore/build/publish/relink/run。
- [ ] native 源修改确实改变执行行为；无修改 rebuild 满足增量规则。
- [ ] Debug/Release、interpreter/R2R、trimming/globalization 的适用组合和 wasm32 对照。
- [ ] 现有 CI 矩阵按已支持能力扩展；重资源 job 独立，不把 zero tests/skip 算 PASS。
- [ ] 支持矩阵、适用 diagnostics、startup/module size/内存基线及可重复证据。

原始计划 §9 的待实现命令仍是接口需求，不能直接列为当前可用命令。具体未来分支只在依赖稳定时创建；以上未启动项目不表示仓库已经存在对应 branch。

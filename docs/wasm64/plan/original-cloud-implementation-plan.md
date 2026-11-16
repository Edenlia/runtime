# CoreCLR wasm64 云端实施计划

**用途：**交给远程云端执行者进行环境准备、分支开发、验证和上游提交。  
**设计基线：**dotnet/runtime `2b5ea9af2991abe307beb855729ab52409d6333f`，2026-11-15。  
**SDK 对照基线：**dotnet/sdk `5947e1a3ccd91c77991df85a763292e109ef4cc2`。  
**执行说明：**本文的现有命令已按该版本的脚本、工程和 CI 配置核对；本轮没有在远程机器实际构建。标为“待实现接口”的命令，是分支需要交付的能力，不能直接当成当前 upstream 已支持。

## 1. 建议采用的组织方式

规划 **dotnet/runtime 内 10 条分支：1 条集成分支 + 9 条功能分支**。进入正式 SDK 集成时，再在 **dotnet/sdk 开 1 条配套分支**。因此跨仓库的主计划是 **11 条分支**，不包括只在发现外部工具链缺陷时才需要的临时复现分支。

准备阶段实际只创建：

- `wasm64/integration`
- `wasm64/target-foundation`

保留一个 detached upstream baseline worktree。后续功能分支在依赖的接口稳定后再开，同时活跃的功能分支控制在 2–3 条。分支是工作组织单位；一次 PR 的边界由可独立评审的行为和测试决定，不预先承诺“9 个功能分支恰好等于 9 个 PR”。

### 首个完整目标

通过普通浏览器 host 和 IL-only WebCIL 加载流程，运行真正的 64-bit CoreCLR interpreter 应用；完成有意义的 native 双向调用、GC/EH，以及实际高地址访问。

Node/corerun 是快速定位与回归通道。它先跑通很有价值，但首个完整目标仍包含普通 browser host、实际浏览器和正常 assembly loading。

### 后续目标

在上述基础上覆盖完整 JS interop、真实 R2R 执行、SDK/workload 发布和持续回归。初始范围选择 native Memory64、browser、当前单 managed thread 模型。WASI、Memory64 lowering compatibility mode、managed multithreading、UE 特定 embedding/foreign-thread entry、卸载重载分别建立后续需求；这份计划不把它们算作已获得的 wasm64 能力。

整个计划从 upstream 缺口出发。已有实验分支可供阅读实现思路；新分支的基线、提交历史和验收结果必须能独立复现。

## 2. 影响计划的上游事实

以下事实决定了顺序，不能只靠目录名称拆任务：

1. **架构入口尚不完整。**`eng/build.sh` 的架构列表只有 `wasm`，browser 分支还会强设该值；runtime test runner 也只认识 `wasm`。因此 `-arch wasm64` 不是现在可直接使用的入口。[构建脚本][build-script]、[runner][runtime-run]
2. **解释器也需要 Crossgen2。**portable call-helper 模式在建立目标类型系统后直接生成 helpers，早于真正的编译流程；它不需要完整 wasm64 RyuJIT 算法。但现有 build graph 会带上 cross-JIT，基础工作必须处理这一构建依赖。[Crossgen2 入口][crossgen-program]、[构建子集][subsets]
3. **IL-only WebCIL 要提前。**普通浏览器解释执行也使用包装模块和 memory/base imports，不能把全部 WebCIL 工作拖到 R2R。[WebCIL wrapper][webcil-wrapper]
4. **现有 Interop 的“绿灯”可能包含大量跳过。**部分 wasm 项目明确关闭测试专用 native corerun；新增 wasm64 后不能通过绕开旧架构条件“获得通过”。应复用现有 native relink testkit，加窄而真实的 ABI 用例。[native testkit][native-testkit]、[Interop wrapper][interop-wrapper]
5. **compiler tests 和执行测试分开。**`ILCompiler.ReadyToRun.Tests` 主要编译、检查产物；真正的 guest execution 要另测。`WasmInterpreterTransitions` 已特别注明：不强制编译时，测试可能全程解释执行仍通过。[R2R tests][r2r-tests]、[transition test][transition-test]
6. **JS 测试默认会启用 R2R。**早期解释器验证要显式 `PublishReadyToRun=false`，并将 `DOTNET_InterpMode=3` 传入浏览器内的 runtime。[JS 测试工程][js-test-project]、[浏览器测试参数][browser-tests]
7. **正式发布涉及 SDK。**当前 SDK 的 R2R compiler resolver 仅解析 `wasm`；它在 runtime 仓库还有镜像实现。采用独立 wasm64 target 时，要配套处理，不能只证明 in-tree override 能用。[SDK resolver][sdk-resolver]

## 3. 分支清单与边界

下表的规模是基于涉及的组件和联动面作出的判断，不是未经实现就预测的修改行数或工期。

| 分支 | 负责的完整功能 | 主要依赖 | 改动面与交付边界 |
|---|---|---|---|
| `wasm64/integration` | 汇合已通过本阶段验收的功能，生成可复现 checkpoint | 所有功能分支 | 长期保留；用于联合验证，不作为大 PR 提交 |
| `wasm64/target-foundation` | target 选择、native/managed 布局入口、工具链与依赖、早期本地产物和测试接线 | upstream baseline | 横跨 build/CMake/type system/test infrastructure；包含 helper-only bootstrap 构建路径 |
| `wasm64/managed-abi` | interpreter/native 调用 ABI、helpers、context/stackwalk/EH 布局 | target-foundation | VM、managed tools、生成代码、native ABI 必须一致；属于核心高耦合改动 |
| `wasm64/gc-memory` | barriers、root 相关内存操作、reservation/growth/accounting、选定 GC 策略 | target-foundation；执行验收需要 managed-abi | 代码面可能较集中，正确性与内存测试成本高 |
| `wasm64/browser-loader` | 普通 host 启动、argv/properties/probes、IL-only WebCIL、基础 heap/string 访问 | target-foundation；联合运行需要 managed-abi 和 gc-memory | 限定启动与加载闭环；公共 JS marshaler 留下一分支 |
| `wasm64/js-interop` | shared marshaling ABI、JS/native 转换、JSImport/JSExport 功能 | browser-loader + managed-abi；高地址测试需要 gc-memory | managed/TypeScript/generated bindings 联动，范围较大 |
| `wasm64/jit-codegen` | RyuJIT wasm64 + relocation + 最小合法编译模块输出 | target-foundation + 已稳定的 ABI | 拥有从 emitter 到 object writer 的最小 producer 链，不能只改 JIT 后声称完整模块测试通过 |
| `wasm64/r2r-modules` | 编译模块的 runtime 消费、加载修补、双向 transitions、partial/composite 实际执行 | jit-codegen + browser-loader + managed-abi + gc-memory | 完成 R2R 的执行闭环；高级 module 情形也在这里扩展 |
| `wasm64/sdk-publish` | runtime/compiler packs、RID/manifest、SDK 消费、publish/native relink | 最小 browser 闭环可先做；完整验收需要 JS/R2R | 正式发布层；早期 in-tree build plumbing 已归 foundation |
| `wasm64/ci-coverage` | 将现有功能测试接入持续验证、配置支持矩阵、记录性能/内存基线 | 按已完成能力逐步接入，最终依赖各功能 | 测试实现随功能分支提交；此分支负责运行编排和文档 |
| dotnet/sdk：`wasm64/target-resolution` | SDK 的 target/RID/crossgen2 选择及配套 SDK tests | target identity 已确定；与 sdk-publish 协同 | 单独仓库、单独 SHA 和验证结果 |

### 不应继续拆开的边界

- **签名生产者与消费者：**VM signature keys、`WasmLowering`、portable helpers、transition layout 不能各自采用不同的过渡格式。
- **共享 JS 参数布局：**managed 端和 TypeScript 端必须同批更新并用一致的 offset/size tests 约束。
- **IL module producer 与 loader：**变更 memory import/base-global 类型时，要共同可实例化。
- **最小编译模块链：**jit-codegen 若要求通过现有 WebCIL/R2R 编译测试，就必须包含所需 writer、relocation 和生成 stub；r2r-modules 再完成 runtime 执行与更广的模块场景。
- **测试与功能：**不能先合入宽度变化，再把对应 correctness tests 全部留给 ci-coverage。

## 4. 依赖顺序与并行方式

~~~mermaid
flowchart TD
    T["Target 与工具链基础"] --> A["Managed / native ABI"]
    A --> G["GC 与内存"]
    A --> B["Browser 与 IL 加载"]
    A --> J["JIT 与编译模块输出"]
    G --> I["浏览器解释器验收"]
    B --> I
    I --> S["JS interop"]
    I --> R["R2R 执行"]
    J --> R
    S --> P["SDK / workload 发布"]
    R --> P
    P --> C["持续验证与支持矩阵"]
~~~

这是最终验收依赖，不要求所有代码都等前一项完成才开始。建议执行节奏：

1. 准备环境、建立 wasm32 基线、记录 ABI 决策。
2. target-foundation 先落地架构选择、产物隔离、bootstrap tools、test runner 入口。
3. managed-abi 冻结最小调用/布局合同。
4. 并行推进 gc-memory、browser-loader；有第三个执行者时可以推进 jit-codegen 的 host 编译测试。
5. 普通浏览器解释器闭环通过后，推进完整 JS interop。R2R 在 producer 可用后独立推进。
6. sdk-publish 的产物选择和 SDK 配套变更可提前开发；完整发布验收等对应能力就绪。
7. CI 从早期 smoke 开始接入，后续增加层级；最终跑完整的适用矩阵。

**同一台机器：**默认同时一个重型 native build，加一个轻量代码/host test 任务。只有实际观测到内存和 I/O 余量后，再增加重型构建并发。高内存测试独占资源窗口。

## 5. 云端环境准备

### 5.1 建议资源

初始执行机建议 Linux x64、16 vCPU、64 GiB RAM、约 500 GiB 可用 SSD。这是本计划为多 worktree、native build、浏览器及高内存测试留出的工作预算，不是官方最低要求，也不是已测得的必需值。

若只有 32 GiB RAM，先单并发构建与普通地址测试；是否能运行后续高内存场景由实测峰值决定。记录容器/cgroup 上限：宿主机显示的 RAM 不一定是任务实际可用上限。准备存放日志和测试结果的持久目录。初期无需购买更多节点，也不需要 GPU。

Linux x64 的选择与当前浏览器自动下载支持相匹配。不要假定 Linux arm64 可以原样复用当前下载配置。[浏览器 provisioning][browser-provision]

### 5.2 仓库、worktree 与日志目录

以下是新机器的首次准备示例；`/work` 换成执行机可写且容量足够的目录。已有 checkout 时先检查其状态，复用或另建目录，不覆盖已有工作。

~~~bash
mkdir -p /work/wasm64
cd /work/wasm64

git clone https://github.com/dotnet/runtime.git runtime-source
cd runtime-source
git remote rename origin upstream
git fetch upstream

WASM64_BASE=2b5ea9af2991abe307beb855729ab52409d6333f
git cat-file -e "$WASM64_BASE^{commit}"

git worktree add --detach ../upstream-baseline "$WASM64_BASE"
git worktree add -b wasm64/integration ../integration "$WASM64_BASE"
git worktree add -b wasm64/target-foundation ../target-foundation "$WASM64_BASE"

mkdir -p /work/wasm64/evidence
git worktree list
~~~

推送 remote 使用本人 fork；等需要备份或建立 review branch 时再配置。不要把现有实验集成分支设成新工作的 base。

各 worktree 使用自己的 `artifacts/bin`、`artifacts/obj`、`CORE_ROOT`、test results 和本地 SDK 测试目录。不要跨 worktree 复制未经校验的 CoreLib、Crossgen2、native wasm 或生成 helper 来“补齐构建”。

上游已有按版本和 host RID 管理的共享 Wasm tool cache，并支持 worktree 共享；无需复制一套自制 cache。先串行 provision 好工具。若测试修补过的 LLVM/Emscripten，使用独立路径和独立 fingerprint，不能覆盖原版本 cache 冒充未修改工具链。[Wasm tool cache][tool-cache]

### 5.3 安装依赖与固定版本

先阅读该 checkout 的 `docs/workflow/requirements/linux-requirements.md`。可以使用仓库依赖脚本，随后验证实际版本：

~~~bash
cd /work/wasm64/upstream-baseline

sudo ./eng/common/native/install-dependencies.sh

cmake --version
clang --version
ninja --version
python3 --version
git --version

./eng/common/dotnet.sh --info
cat global.json
cat src/mono/browser/emscripten-version.txt

./build.sh -os browser -arch wasm -c Release -subset provision.emsdk
~~~

该基线的 `global.json` 指向 `12.0.100-alpha.1.26557.102`；Emscripten pin 为 `6.0.2`；Linux requirements 要求 CMake 至少 3.26。使用仓库脚本选择 SDK/Emscripten，不安装任意 “latest” 来替代它们。[Linux requirements][linux-requirements]、[global.json][global-json]、[Emscripten pin][emscripten-pin]

Node 和浏览器分别记录实际 executable path、版本和启动参数。优先采用仓库下载的浏览器及当前构建配置选用的 Node；如果 runner 最终取 PATH 中的 Node，必须明确记录。用工具链微型 probe 证明 Memory64/所需 Wasm features 可用，不能只凭版本号判定。

### 5.4 工具链微型 probe：先排除外部 ABI 问题

在正式修改 runtime 前，建立可独立复现的 native C/C++ probe，记录：

- `sizeof(void*)`、`sizeof(size_t)`、`sizeof(intptr_t)`、函数指针大小和关键 aggregate 的 size/alignment。
- 标量、混合整数/浮点、struct 参数/返回、间接调用和 callback 的真实签名。
- 输出模块的 memory address type、table type、imports/exports、required features。
- Node 和目标 Chrome 是否能实例化并执行；所需 engine flags 逐项记录。
- 工具链采用的 pointer/BigInt/Number 转换方式和 native relink 约定。

Memory64 与 table64 不能凭名称混为一谈；以选定工具链实际输出、模块边界需要和规范分别确定。[Memory64 规范说明][memory64-spec]

若 stock toolchain 有缺陷：先保存最小复现、确切失败、候选上游修复版本。选择更新工具链还是保留临时 patch 要形成显式记录；patched-toolchain lane 的结果不能充当未修改工具链验收。

## 6. 开始编码前需要形成的合同

创建一份简短的设计记录，例如 `docs/design/features/wasm64-bringup.md`（建议新文件，最终目录按 upstream 约定调整）。以下项目给出建议默认值，并明确真正需要协调的部分。

| 问题 | 本计划默认 | 必须确定的输出 |
|---|---|---|
| 初始执行模型 | browser + native Memory64 + 单 managed thread | 功能与浏览器支持矩阵，显式列出延后的能力 |
| 内部架构名称 | 使用 `wasm64` 区分 `wasm` | CLI/type-system/native macros/产物目录的映射 |
| RID | 开发时拟用 `browser-wasm64` | 上游确定正式名称与 pack/RID graph 规则；不要为此自动新增公共 `Architecture` enum |
| native/module ABI | 匹配选定工具链 | pointer、函数指针、table、memory、globals、hidden args、alignment/retbuf 的合同 |
| metadata | 保留合理的固定宽度字段 | 对 RVA、长度、索引等逐项说明上下界与溢出拒绝；只在格式语义确实变化时改版本 |
| JS 值语义 | 保持已有公共 API 语义；内部不截断地址 | Number 精确范围、BigInt 边界、range checks、handle sentinel 的分别处理 |
| shared JS layout | managed 与 JS 共同设计并验证 | 字段 offsets/size/alignment；不预先指定 56-byte 等未经推导的布局 |
| GC 与线性内存 | 先支持一个明确可验证的配置 | reservation/growth/limit 行为；用数据选择 region/segment 策略，不因 64-bit 就机械套桌面默认 |
| R2R 启用方式 | 先完成解释器；R2R 未就绪时明确不支持 | helper-only bootstrap 与完整编译路径的构建边界 |
| 产物兼容 | wasm32/wasm64 明确区分 | 错误架构/错误模块合同的早期诊断，避免链接或运行时静默混用 |

上游 Wasm reservation 当前会分配并清零内存，选到 64-bit target 也会影响 GC 默认策略。先量化 reservation、启动占用、growth 和分配失败，再决定具体策略。[Wasm GC][gc-wasm]

如果修改 JIT/EE interface，按仓库规则更新 JIT-EE version GUID 和相关 generated glue；不要虚构一个全局 “wasm64 ABI version” 字段。WebCIL 是否需要格式版本变化由实际兼容性变更决定。[JIT interface 更新规则][jit-interface]

## 7. 每条功能分支的具体工作单

### 7.1 target-foundation

**主要入口：**`eng/OSArch.props`、`eng/build.sh`、`eng/native/configureplatform.cmake`、`eng/native/configurecompiler.cmake`、`src/coreclr/clrdefinitions.cmake`、TargetArchitecture/TargetDetails、Wasm build targets、runtime/compiler tests 的架构选择。

交付：

- 区分 Wasm family 与 32/64-bit pointer width；browser 不再覆盖显式选择的 wasm64。
- 让 CoreLib、native runtime、managed tools、native dependencies 和本地 pack 路径使用一致目标。
- 接通 ICU 等 native 依赖的 wasm64 构建/获取路径；缺少目标依赖时明确失败。
- 处理 helper-only/bootstrap 的构建图。不能为生成 helpers 先强迫尚未实现的 wasm64 JIT 通过，也不能用 wasm32 Crossgen2 输出替代。
- target-aware 的 runner、CORE_ROOT、native testkit、compiler test fixtures、生成 helper 输出和本地 browser pack 选择。
- 修正 corerun 在 wasm64 上的 memory limit、BigInt/HEAP64 等选项。当前 Node/corerun 有 4 GiB cap 和 wasm32 专用设置，需要目标区分。[corerun 配置][corerun-cmake]
- 新入口必须明确报告实际目标；错误参数不能被当成测试成功。
- 不把未完成的 wasm64 R2R 暴露为可用能力。

验收：

- wasm32 基线无新增回归；host 端 layout/target selection tests 实际执行。
- wasm64 选择和产物检查真实反映 64-bit。
- helper-only 构建路径独立于完整 wasm64 codegen。
- 若本阶段仍因未实现的 runtime/ABI 无法完整运行，准确记录阻塞；不要求把下游全部塞进这一条分支。

### 7.2 managed-abi

**主要入口：**interpreter native-sized paths、`vm/wasm/helpers.cpp`、`callingconvention.h`、`callhelpers.hpp`、portable helper generators、`WasmLowering.cs`、transition blocks、PAL CONTEXT、managed asm offsets。

交付：

- native int/pointer/byref、generic dispatch、hidden context、runtime-async continuation 的一致表示。
- helper signature key、C/C++ signature、managed lowering 和 VM dispatch 同步修改。
- saved context、stack walking、GC root reporting、EH/unwind 所需的宽度和 offsets。
- 不把虚拟 IL offset、flags、metadata token 等非指针字段全部扩大。
- 在现有 testkit 上新增 native ABI 专项，且 wasm32 也运行。
- 同线程可控的真实 suspend/resume 用例；至少一个 continuation 在 suspended 状态经历 GC 后恢复。同步完成的 await 不算覆盖。

分两级验收，避免与 GC 分支形成循环依赖：

- **接口 checkpoint：**host layout/helper tests、producer/consumer 的共同布局约束、wasm32 回归，以及当时能独立执行的最小 wasm64 ABI 用例。helper 重新生成可复现；参数布局显式覆盖两种目标，不依赖宿主 pointer size。这个 checkpoint 通过后即可创建 gc-memory。
- **与 gc-memory 联合验收：**arithmetic/object/array/generic/interface/delegate/EH 的解释器集合，native 实际读写、双向调用、aggregate/retbuf/byref、callback 内 GC、root reporting，以及 suspended continuation 经 GC 后恢复。未满足 GC 前置的项目明确标为 BLOCKED，不能在早期 ABI 分支上提前宣称通过。

### 7.3 gc-memory

**主要入口：**`src/coreclr/runtime/wasm/writebarriers.cpp`、`src/coreclr/gc/wasm/gcenv.cpp`、相关 GC 默认配置与会计路径。

交付：

- stackless barriers、address comparison、card-table 地址计算、reference stores 的宽度正确性。
- 保留 card bytes/flags 的原始语义。
- 选定 GC 配置下的 reservation、growth、limit、allocation failure。
- 支持普通地址与高地址 roots/objects/interior references/pinned buffers。
- 精确区分 native linear-memory allocation 与 managed GC heap：一种高地址成功不能代替另一种。

验收：

- 普通地址下 allocation/collection/EH/callback 行为正确。
- 实际高地址对象和 roots 经所选 collector 支持的 collection 后仍正确。
- 有界压力和 growth；地址、校验值、GC 前后状态、峰值内存均有证据。
- 超出配置预算时得到定义好的失败，不能越界、截断后错误成功或把测试进程 OOM kill 计作通过。

### 7.4 browser-loader

**主要入口：**Common JavaScript host/asset loading、基础 memory/string helpers、`WebcilWasmWrapper.cs`、converter 和 native loader/decoder。

交付：

- runtime startup、argv/properties、assembly probes、ICU/PDB 等指针传递。
- IL-only WebCIL 的 memory imports、image-base globals、pointer parameters。
- 普通 host 通过正常 asset manifest 下载和加载 framework/test assemblies。
- architecture/module ABI 不匹配时给出明确诊断。
- 在既有 Wasm.Build.Tests 中增加 CoreCLR/no-workload 的最小 wasm64 browser fixture（建议名称 `Wasm64BasicTests`，这是待新增用例）。
- 最小入口参考现有 `src/mono/wasm/testassets/EntryPoints/minimal_main.js` 和 `ReplaceMainJsWithMinimalRunMain()`；先不使用模板默认的 `setModuleImports` / `getAssemblyExports`，防止启动门槛提前依赖完整 JS interop。在 `.create()` 前设置 `.withEnvironmentVariable("DOTNET_InterpMode", "3")`，经正常 host 执行 managed Main；其中可以调用已完成的 P/Invoke 用例。

验收：

- 真实 Chrome，经普通 host 与 IL WebCIL 启动，传递参数并执行 managed 代码。
- 同一最小应用分别验证普通 DLL 与 IL WebCIL 资产路径，断言 `IntPtr.Size == 8`、argv/Unicode/environment value 与退出结果。
- 显式 interpreter-only；fixture 创建 runtime 前设置 `DOTNET_InterpMode=3`。
- 包含 meaningful native interop 和 GC/EH 的浏览器执行；高地址专项按资源窗口单独运行。
- 不能仅凭裸 DLL + corerun/Node 宣称普通浏览器加载路径完成。

### 7.5 js-interop

**主要入口：**`JSMarshalerArgument`、JS interop TypeScript types/marshal/GC handles、shared heap/string access、generated imports/exports。

交付：

- managed/JS layout 在同一分支共同更新；建立 offset/size/assertions。
- 去除地址上的 32-bit bitwise 截断，同时保留计数/标志/handle 语义。
- 指针、native int、long/ulong、opaque handles 分别设计转换和 range checks。
- heap view 在 memory growth 后刷新；不复用失效 view。

验收：

- 现有 JS unit project 的实际浏览器执行。
- numeric、strings、arrays/spans、delegates、promises、exceptions、对象生命周期。
- 2 GiB/4 GiB 附近的地址边界、真实高地址 buffers、growth 后继续 marshal。
- 非解引用的数值转换另测 safe-integer 边界；不能用一个超大数值模拟成功代替高地址读写。
- shared JS/native utilities 影响到 Mono wasm32 时，补对应 Mono 回归；不把这扩大成 Mono wasm64 实施。

### 7.6 jit-codegen

**主要入口：**`targetwasm.h`、codegen/emitter、JIT/EE relocation 合同、managed `Relocation.cs`、最小 WebCIL object writer/module emission、必要的生成 stub。

交付：

- wasm64 target、native-sized instructions、addressing、frame/stack layout。
- address relocations 和其 LEB/SLEB 编码；与索引、固定 metadata 分开处理。
- Crossgen2 能产出 validator 接受、imports/signatures 符合合同的最小 wasm64 编译模块。
- compiler fixtures 显式实例化 Wasm64 target，不能继续硬编码 Wasm32 或自动 skip。

验收：

- host unit/layout/emission/relocation tests。
- 对真实目标 CoreLib/libs 运行适用的 R2R compiler tests。
- 验证最小 module、address relocations 高位值、边界与溢出；不需要靠构造巨大文件才能验证全部编码边界。
- **这一阶段的“模块可编译”不表示 R2R guest 已执行。**

### 7.7 r2r-modules

**主要入口：**compiled-module loader、memory/table/global imports、base fixups、interpreter↔R2R/native transitions、runtime globals、partial/composite module 合同。

交付：

- runtime 正确实例化、修补和消费编译模块。
- 真实双向 transitions，与前面已经定义的 calling convention 一致。
- partial R2R、composite、未编译方法 fallback、跨程序集调用。
- 编译代码下的泛型、GC/EH、native callback、真正 suspend/resume。
- 根据执行场景继续补 producer 所需格式能力，保持与 runtime 同步。

验收：

- `WasmInterpreterTransitions` 扩展到 wasm64，实际执行编译方法。
- 每个关键方向都有记录：interpreted→compiled、compiled→interpreted、compiled→native、native callback→managed。
- 使用方法级 trace、断点或测试可验证的 compiled-body 执行标记证明命中编译代码。
- 同一 fixture 的 `DOTNET_ReadyToRun=0` 负对照使该 compiled-body 证据消失，并仍保持预期语义。
- 不能用加载日志、文件存在或 Crossgen2 exit 0 代替此验收。[执行证据边界][r2r-execution-evidence]

### 7.8 sdk-publish 与 SDK 配套分支

**runtime 侧：**RID graph、runtime/compiler packs、WebAssembly SDK/manifest、build tasks、publish 和 native relink；同时检查 runtime 内镜像的 compiler resolver。  
**SDK 侧：**target parsing、compiler/pack selection、测试样例和负例。

交付：

- in-tree override 与真正安装 workload 的两种路径明确区分。
- host Crossgen2 pack 能选择 wasm64 cross compiler/target。
- pack 内容、文件名/目录、RuntimeIdentifier、runtime architecture 和实际模块一致。
- clean restore/build/publish、native relink、incremental rebuild。
- Debug/Release、interpreter/R2R、trimming、globalization 的适用组合。

验收：

- 从该 SHA 重新打包并创建独立测试 SDK；完整运行 workload lane。
- 运行输出应用，包括真实 JS 和 native call；不能只检查 publish 命令返回成功。
- 修改 native 源文件后，行为变化确实反映在运行结果；无修改 rebuild 应符合既有增量规则。
- 错误架构或缺失 compiler pack 明确失败。
- 原有 wasm32 项目仍能按原配置 build/publish/run。
- 默认支持的 trimming/globalization 路径不能被统一关闭后宣称支持完成；不适用项要记录原因。

### 7.9 ci-coverage

交付：

- 每个功能分支自己的测试已随代码合入。
- PR 快速 lane、集成 lane、高内存 lane、扩展矩阵 lane。
- 浏览器/toolchain pin、实际运行参数、test-count/skip 检查。
- startup/module size/峰值内存基线；只比较相同源码和设置。
- applicable diagnostics smoke，并与 #134337 的更广工具工作协调；不把全部 debugger/Hot Reload 项目重复承诺在 wasm64 port 内。

验收：

- 全新工作目录从源码和已声明依赖复现。
- CI 配置与本地命令一致；不能把尚未运行的远程 CI 标为通过。
- 支持矩阵中每项都能追溯到 build/test 记录。

## 8. 当前 upstream 可执行的基线命令

**本节全部为 wasm32 基线。**所有命令从对应 worktree 的仓库根运行。建议先使用全 Release，减少不同 configuration 的产物选择干扰。

### 8.1 产品、packages 与 Release 测试工具

~~~bash
./build.sh -os browser -arch wasm -c Release \
  -subset clr+libs+packs \
  /p:BuildCrossgen2HostPackForWorkloadTesting=true

./build.sh -os browser -arch wasm -c Release \
  -subset provision.emsdk+tasks
~~~

`clr` 已包含 CoreCLR 的 package 路径；browser 下会引用 WebAssembly SDK、templates、manifest 等。不要为 CoreCLR 工作照搬旧 Mono 打包入口。`BuildCrossgen2HostPackForWorkloadTesting=true` 是为 workload 测试本地 feed 准备 host Crossgen2 pack 的显式选择。[子集与包依赖][subsets]、[CoreCLR packages][coreclr-packages]

### 8.2 两个真实 runtime 小测试

~~~bash
BuildAllTestsAsStandalone=true ./src/tests/build.sh \
  -os browser -wasm -release -priority1 \
  /p:LibrariesConfiguration=Release \
  /p:HostConfiguration=Release \
  -test:baseservices/exceptions/simple/finally.csproj \
  -test:GC/Features/KeepAlive/keepaliveother/keepalivetry.csproj

DOTNET_InterpMode=3 ./src/tests/run.sh wasm release \
  --node --interpreter --sequential \
  --tree=baseservices/exceptions/simple

DOTNET_InterpMode=3 ./src/tests/run.sh wasm release \
  --node --interpreter --sequential \
  --tree=GC/Features/KeepAlive/keepaliveother
~~~

说明：

- `finally.csproj` 是 priority 1，不能省略 `-priority1`。
- standalone 模式避免选中的 merged 子项目缺少可发现的单独执行入口。
- `--tree` 一次一个 subtree，分开运行。
- `DOTNET_InterpMode=3` 明确禁止 JIT/R2R fallback；`--interpreter` 保留 runner 相应逻辑。[interpreter 配置][interp-config]
- `keepalivetry` 不适用于 AnyGCStress；这组命令仅是普通 GC/EH 基线。
- 这两个小测试不是 native ABI、高地址或完整 runtime suite 验收。

### 8.3 Call-helper 可复现生成

~~~bash
src/coreclr/vm/wasm/generate-coreclr-helpers.sh \
  -c Release --target-os browser

git diff --exit-code -- src/coreclr/vm/wasm
~~~

先有匹配的 Release 产物再生成。当前脚本默认包含 browser 和 WASI，故显式选 browser。用于提交的生成表采用 Release 与 CI 对齐。当前脚本还没有架构参数；wasm64 的参数、输入和输出隔离由基础/ABI 分支补齐。[helper 文档][helper-doc]

若该基线本身生成后有 diff，保留 diff 和日志、调查原因，不能把它当作 wasm64 已完成或直接覆盖原基线。

### 8.4 真实浏览器的 JS interop 基线

~~~bash
./dotnet.sh build \
  src/libraries/System.Runtime.InteropServices.JavaScript/tests/System.Runtime.InteropServices.JavaScript.UnitTests/System.Runtime.InteropServices.JavaScript.Tests.csproj \
  -c Release -t:Test \
  -p:TargetOS=browser \
  -p:TargetArchitecture=wasm \
  -p:RuntimeFlavor=CoreCLR \
  -p:Scenario=WasmTestOnChrome \
  -p:InstallChromeForTests=true \
  -p:PublishReadyToRun=false \
  -p:WasmXHarnessMonoArgs=--setenv=DOTNET_InterpMode=3
~~~

最后一个参数会经 XHarness/test host 设置到浏览器内的 runtime；仅在宿主 shell 设置环境变量并不能证明已传入浏览器。[浏览器测试参数][browser-tests]

### 8.5 WebCIL parser 与完整 workload smoke 分开

无 workload 的 parser 测试：

~~~bash
./dotnet.sh build \
  src/mono/wasm/Wasm.Build.Tests/Wasm.Build.Tests.csproj \
  -c Release -t:Test \
  -p:TargetOS=browser \
  -p:TargetArchitecture=wasm \
  -p:RuntimeFlavor=CoreCLR \
  -p:TestUsingWorkloads=false \
  -p:XUnitClassName=Wasm.Build.Tests.WebcilInWasmSizesTests
~~~

这只能作为 parser/size 测试记录，不能代替 browser app smoke。

完成 `8.1` packages 后，完整 workload 的实际浏览器 smoke：

~~~bash
./dotnet.sh build \
  src/mono/wasm/Wasm.Build.Tests/Wasm.Build.Tests.csproj \
  -c Release -t:Test \
  -p:TargetOS=browser \
  -p:TargetArchitecture=wasm \
  -p:RuntimeFlavor=CoreCLR \
  -p:TestUsingWorkloads=true \
  -p:InstallWorkloadForTesting=true \
  -p:WorkloadsTestPreviousVersions=false \
  -p:InstallChromeForTests=true \
  -p:XUnitMethodName=Wasm.Build.Tests.ModuleConfigTests.ConfigLoadedCallbacks
~~~

当前 CoreCLR WBT 默认 `TestUsingWorkloads=false`，且该模式只选择 `category=no-workload`。因此不能拿一个 workload-only method filter 配 no-workload mode，再用零执行量宣称成功。[WBT 工程][wbt-project]

后续修改 product/packages 后，应重新构建包并让测试 SDK 安装新产物；不能沿用旧测试 SDK 的成功结果。不要把 CI 已准备好包时使用的禁用准备参数原样复制到首次本地执行。

### 8.6 Host managed tools 和 R2R 编译基线

host managed tool tests：

~~~bash
./build.sh -s clr.toolstests -c Release -build -test
~~~

foundation 内循环可聚焦现有类型布局测试，并在其中增加独立 Wasm64 context：

~~~bash
./dotnet.sh test \
  src/coreclr/tools/aot/ILCompiler.TypeSystem.Tests/ILCompiler.TypeSystem.Tests.csproj \
  -c Release \
  --filter "FullyQualifiedName~ArchitectureSpecificFieldLayoutTests"
~~~

这条 host unit-test 命令不同于 runtime guest 的 `src/tests` runner；它验证的是显式构造的目标布局。现有类已有 Wasm32 context，新增 Wasm64 时应保留双架构断言。[managed tools 测试指引][managed-tools-tests]

已有匹配 browser Release CoreLib/libs 后，运行 browser R2R compiler tests：

~~~bash
./build.sh -s clr.r2rtests -os browser -arch wasm \
  -c Release -lc Release -test
~~~

这些 tests 使用目标 CoreLib/libs；只设置 TargetRid 不足以选择正确测试输入。现有 fixture 的 Wasm32 硬编码和 `IsWasmTarget` 条件必须在 wasm64 分支改造后才能复用。[R2R 测试工程][r2r-tests]

### 8.7 Checked runtime 开发配置

GC/ABI/stackwalk 开发优先用 Checked CoreCLR，libraries 保持 Release；对应配置在当前 CI 已有使用。[runtime tests CI][runtime-ci]

~~~bash
./build.sh -os browser -arch wasm -c Release -rc Checked \
  -subset clr+libs+packs

./build.sh -os browser -arch wasm -c Checked \
  -subset provision.emsdk+tasks
~~~

随后 `8.2` 测试构建改 `-release` 为 `-checked`，runner 改为 `wasm checked`，仍指定 LibrariesConfiguration/HostConfiguration=Release。

库/browser tests 需要 Checked runtime 时，在对应命令额外加 `-p:RuntimeConfiguration=Checked`。helper 提交表仍用单独的全 Release 生成环境。每份记录必须同时写明 runtime、libraries、host 和 test tasks 配置。

## 9. wasm64 分支必须交付的命令接口

**本节是待实现接口。上游基线当前不能直接运行。**建议沿用原入口，不写一套绕开上游 test infrastructure 的私人 runner。

### 9.1 wasm64 产品与 runtime 测试

~~~bash
./build.sh -os browser -arch wasm64 -c Release -rc Checked \
  -subset clr+libs+packs

./build.sh -os browser -arch wasm64 -c Checked \
  -subset provision.emsdk+tasks

BuildAllTestsAsStandalone=true ./src/tests/build.sh \
  -os browser -wasm64 -checked -priority1 \
  /p:LibrariesConfiguration=Release \
  /p:HostConfiguration=Release \
  -test:baseservices/exceptions/simple/finally.csproj \
  -test:GC/Features/KeepAlive/keepaliveother/keepalivetry.csproj

DOTNET_InterpMode=3 ./src/tests/run.sh wasm64 checked \
  --node --interpreter --sequential \
  --tree=baseservices/exceptions/simple

DOTNET_InterpMode=3 ./src/tests/run.sh wasm64 checked \
  --node --interpreter --sequential \
  --tree=GC/Features/KeepAlive/keepaliveother
~~~

实现时同时处理 shell runner、C# runner、test build argument parser、Wasm launcher 条件、CORE_ROOT 选择、native relink helpers 和 artifact architecture。不要用会强制 wasm 的旧 browser shorthand。

后续 wasm64 full build 能否完成，取决于对应分支组合；foundation 的交付不等于这些 runtime tests 已通过。若 helper-only bootstrap 采用显式开关，必须把开关及其支持范围补入最终 runbook，不能隐含地使用另一种架构。

### 9.2 新增 native ABI 测试

建议新增以下项目，覆盖 wasm32 和 wasm64，而不是只给 wasm64 特判通过：

~~~text
src/tests/Interop/WasmNativeAbi/WasmNativeAbi.csproj
src/tests/Interop/WasmNativeAbi/Program.cs
src/tests/Interop/WasmNativeAbi/CMakeLists.txt
src/tests/Interop/WasmNativeAbi/WasmNativeAbiNative.cpp
~~~

使用现有 `CMakeProjectReference` 和 testkit，并明确设置 `<RequiresProcessIsolation>true</RequiresProcessIsolation>`，保证默认 merged/Helix 流程也携带并执行测试专用 corerun。本地 standalone 成功不能代替此配置。native assets 缺失必须使专项测试失败。

**项目创建且测试入口支持 wasm64 后：**

~~~bash
BuildAllTestsAsStandalone=true ./src/tests/build.sh \
  -os browser -wasm64 -checked \
  /p:LibrariesConfiguration=Release \
  /p:HostConfiguration=Release \
  -test:Interop/WasmNativeAbi/WasmNativeAbi.csproj

DOTNET_InterpMode=3 ./src/tests/run.sh wasm64 checked \
  --node --interpreter --sequential \
  --tree=Interop/WasmNativeAbi
~~~

必须断言实际 native side effect、读写校验和 callback。`__TestNativeAssetsLinked=true` 是辅助证据，不能单独代替调用结果。

### 9.3 wasm64 浏览器与 JS

先创建 `browser-loader` 的 no-workload fixture，它应使用第 7.4 节的无公共 JS interop 入口、普通 host、IL WebCIL，并在创建 runtime 前设置 interpreter-only。不要把 WBT 的 `ServerEnvironment` 当作浏览器内 runtime environment。完成后再使用 `Wasm64BasicTests` 的实际 class filter；在文件尚未建立前，不把该 filter 当现有测试。

JS gate 使用 `8.4` 的项目与参数，将 `TargetArchitecture` 改为 `wasm64`；Checked runtime 加 `RuntimeConfiguration=Checked`。这一改动只有在 build/pack/test plumbing 全部接好之后有效。

### 9.4 wasm64 compiler 与 R2R execution

有匹配的 Checked runtime/CoreLib 和 Release libraries，且 compiler 分支完成后：

~~~bash
./build.sh -s clr.r2rtests -os browser -arch wasm64 \
  -c Checked -lc Release -test
~~~

真实 transition 项目已存在；把它纳入 wasm64 后：

~~~bash
BuildAllTestsAsStandalone=true ./src/tests/build.sh \
  -os browser -wasm64 -checked \
  /p:LibrariesConfiguration=Release \
  /p:HostConfiguration=Release \
  -test:readytorun/wasm/WasmInterpreterTransitions/WasmInterpreterTransitions.csproj

env -u RunInterpreter \
    -u DOTNET_InterpMode \
    -u DOTNET_Interpreter \
    -u DOTNET_ReadyToRun \
  ./src/tests/run.sh wasm64 checked \
  --node --sequential \
  --tree=readytorun/wasm/WasmInterpreterTransitions
~~~

该测试的 `AlwaysUseCrossGen2` 是现有强制编译机制。执行前还要确认测试 fixture/runtime config 没有继承 interpreter-only 设置。compiled-body 的证据机制应随分支实现并记录。

再用 `DOTNET_ReadyToRun=0` 跑同一场景作为负对照，并确认此变量实际进入 guest runtime：编译方法的命中证据应消失。对照本身不是“R2R 失败测试”，它用于检查证据是否真的区分执行方式。

完成 R2R 后，JS browser 测试增加第二条 lane：去掉 `PublishReadyToRun=false` 和强制 `InterpMode=3`，使用正常 mixed R2R/interpreter 配置，同时保留解释器 lane。

### 9.5 SDK 配套分支：已有执行入口，新增 wasm64 用例

到正式 SDK 集成阶段再建立该 checkout：

~~~bash
cd /work/wasm64
git clone https://github.com/dotnet/sdk.git sdk-source
cd sdk-source
git switch -c wasm64/target-resolution \
  5947e1a3ccd91c77991df85a763292e109ef4cc2

./build.sh -c Release
~~~

SDK 仓库的 `AGENTS.md` 要求本地测试遵循它的 `run-tests` 指引；该仓库使用集中 runner，并测试当前 redist 产品。实现者进入仓库后仍需读取该 checkout 的完整指引。下面是本计划核对过的现有入口：[SDK 测试指引][sdk-test-skill]

~~~bash
./.dotnet/dotnet scripts/RunTests.cs -- \
  --project test/Microsoft.NET.Build.Tasks.Tests/Microsoft.NET.Build.Tasks.Tests.csproj \
  --configuration Release \
  --filter "FullyQualifiedName~GivenAResolveReadyToRunCompilers"

./.dotnet/dotnet scripts/RunTests.cs -- \
  --project test/Microsoft.NET.Publish.Tests/Microsoft.NET.Publish.Tests.csproj \
  --configuration Release \
  --filter "FullyQualifiedName~GivenThatWeWantToPublishReadyToRun" \
  --test-binlogs
~~~

这两个 class 现在已经存在，但其中的 wasm64 正/负例需要随配套分支增加。生产代码改变后先重新构建 redist，再运行 tests；只重建 test project 可能继续测试旧 SDK。[SDK resolver tests][sdk-resolver-tests]、[SDK publish tests][sdk-publish-tests]

最终联合验收必须同时选择该分支构建的 SDK 和 runtime 分支的新包。runtime 的 WBT 默认构造自己的测试 SDK，并不会因为旁边存在 `sdk-source` 就自动使用修改过的 resolver。由 sdk-publish 分支明确接入自建 SDK 的测试通路，或由 SDK 侧 fixture 使用新 runtime 本地 feed；记录实际 SDK 路径、resolver assembly 与 pack hash。没有这份双仓库对应证据，不能把两个各自通过的测试汇总成端到端通过。

## 10. 测试矩阵与各类“通过”的含义

### 10.1 每类功能必须覆盖什么

| 测试层 | 必须证明 | 常见误判 |
|---|---|---|
| 目标/模块 | 真正 memory64、native/managed pointer size 一致、正确 dependencies | RID/目录名叫 wasm64 就算完成 |
| interpreter | 对象、数组、native int、泛型、dispatch、EH，且全解释器模式 | 只跑 HelloWorld 或被 R2R 接管 |
| native ABI | 真实静态 relink、双向调用、aggregate/retbuf/byref、合法 GC transition | 缺 native assets 后自动 skip |
| 高地址 | 实际地址超过 `0xffffffff`，真实读写并校验 | 仅传递一个大整数或设置最大内存 |
| 高地址 GC | managed 高地址对象/roots/interior refs 经 GC 后仍正确 | 只有 native malloc 高地址 |
| growth | 实际 memory.grow，managed/native/JS 继续工作，views 正确刷新 | 只修改 ALLOW_MEMORY_GROWTH |
| 压力 | 有界重复分配/存活/回收，记录 seed、次数、峰值与失败模式 | 一次高地址访问替代长期压力 |
| 普通 browser | normal host + manifest + IL WebCIL + 实际 browser | 只有 Node/corerun |
| JS interop | 真实 generated imports/exports、字符串/容器/异步/异常 | 只有 layout 或 helper unit tests |
| R2R 编译 | 模块与 relocations/signatures 正确 | 编译成功就称 R2R 已运行 |
| R2R 执行 | 方法级 compiled-body 证据及双向 transitions | image-load log 或全解释执行也通过 |
| SDK | 新安装 workload 的真实 build/publish/relink/run | 本地 paths override 替代正式 package 验收 |

### 10.2 Native ABI 用例要求

最小矩阵包含：

- `nint`/`nuint` 与 `long`/`ulong` 分别验证；指针和普通 i64 不能互相替代。
- pointer 参数/返回、`ref`/`out`、pinning、native 对真实数据读写。
- supported blittable structs、mixed integer/float、不同参数数量、retbuf。
- managed→native、native→managed、嵌套往返、callback 中允许的 GC。
- managed EH、callback 内部 catch/finally。
- delegate/function-pointer 签名与 toolchain table 合同一致。

不要为了测试“极限路径”违反本身的 ABI 契约：例如 suppress-GC-transition 的叶子调用，不应在该路径回调 managed；未定义的跨 native boundary 未处理异常，不作为初始 port 必需语义。

### 10.3 高地址与大内存：安排三个独立 job

**高地址正确性 job**

- 让真实 linear-memory allocation 地址跨过 4 GiB。
- 打印十六进制地址、memory byte length、前后校验值和完整 pointer round-trip。
- 检查 2 GiB/4 GiB 边界附近、相同低 32 位的不同有效地址不会误别名。
- managed heap 高地址对象单独覆盖；记录 collector、roots、interior byref、pinning。
- 不能要求 function-table index 也跨过 4 GiB；那是另一个合同。

**growth / GC 压力 job**

- 小一些的 initial heap，多轮增长，固定 seed 和迭代次数。
- 覆盖存活对象、回收、GC callback、JS view refresh、真正 async suspension。
- 在选定 collector 支持的情况下覆盖 young/full/compacting collection。
- 不无条件套用桌面 GCStress；只用明确适配的测试和配置。

**大 live-set / 内存限制 job**

- 当目标包含大于 4 GiB 的实际应用数据时，通过多对象/多 buffer 建立并校验该 live set，不能假设单个 managed array 可以超过其现有元素/长度限制。
- 记录实际触达字节量、linear-memory 大小、进程 RSS/容器峰值及 GC heap 数据。
- sparse 高地址不等于大 physical/live-set；linear-memory reservation 也不是 RSS。
- 单独测试接近 limit 的可控失败。资源不足记为环境阻塞或未验收。

普通 app relink 的现有属性是 `EmccMaximumHeapSize`；预建 browser host 使用 `BrowserHostMaximumHeapSize`。两者不是任意可互换的参数。初次高地址实验可从 8 GiB 线性内存上限的候选配置开始，须先通过工具链/引擎验证并检查最终 linker args；该数值是实验预算，不是产品默认值。[app link 参数][browser-targets]、[native defaults][native-wasm]

不得把现有 `MemoryTests` 中只验证 build failure 的用例，或 GC/LargeMemory 下的 support-library 工程，当成已经执行了大内存场景。专项 job 必须有地址与触达断言。

### 10.4 运行频率

| 频率 | 建议范围 |
|---|---|
| 每个有行为变化的 commit | 相关 host/unit tests + 一组最小 wasm32 回归 + 当前已可运行的 wasm64 专项 |
| 每次并入 integration | Node interpreter、普通 browser host、native ABI、相关 JS/R2R lane、wasm32 对照 |
| 每个可交付 checkpoint | Checked 与 Release、真实高地址、growth、GC/EH/async、当前 workload path |
| 重型资源窗口 | 大 live-set/压力、适用 runtime/library suite、扩展浏览器、性能/size/内存 |
| 正式上游 ready-for-review 前 | 对 PR 实际 base/head 重跑必要门槛，附清楚的未覆盖项和 baseline failures |

不跑盲目的全笛卡尔积。先固定 Linux x64 build host + 一个 repo-pinned Chrome，保留 Node fast lane；第二浏览器和其他宿主 OS 按声明支持范围增加。任何尚未支持的环境不计为 PASS。

## 11. 阶段验收与推进条件

| 阶段 | 交付物 | 通过后可以继续 | 阻塞时如何处理 |
|---|---|---|---|
| 环境与 wasm32 基线 | 工具/资源清单、源码 SHA、产品和关键 baseline 结果 | foundation 开发 | 先区分环境问题与原有 upstream failure，保留最小复现 |
| Target/ABI 接口可验证 | 目标映射、helper-only 构建、host layout/helper 测试及当时可独立执行的最小 ABI；GC 相关运行测试暂列联合验收 | GC/browser/codegen 并行 | 不靠错误架构产物填空，不掩盖不支持路径 |
| 浏览器解释器闭环 | normal host + IL WebCIL + native/GC/EH + 高地址 | 扩大 JS/library 与 R2R 执行 | 按 runner/ABI/GC/loader 分层定位 |
| JS/compiled execution | 完整 JS lane、实际 R2R 方法执行、mixed transitions | 正式 SDK/publish 联合验收 | 编译与执行分别标状态，防 silent fallback |
| 发布与回归 | 新包、新测试 SDK、build/publish/relink/run、wasm32 回归 | 准备上游 PR 和支持矩阵 | 镜像源码/SDK resolver 同步，检查实际选中的包 |
| 可维护交付 | 适用 CI、文档、可重复证据、明确剩余限制 | 逐项向上游提交 | 不把实验结果扩大成未测试的平台承诺 |

这些 gate 约束证据和依赖；正常修复与可逆实现选择不必每一步重新等用户确认。真正涉及公共 ABI、正式 target identity 或外部工具链选择的分歧，用具体试验和选项提交设计讨论。

## 12. 集成、分支更新与上游 PR 流程

### 12.1 建立 checkpoint，而不是不断互相 merge

- 功能分支从已记录的 upstream 或必要依赖 checkpoint 建立，记录 `base_sha`。
- integration 按依赖顺序合入已验收的 feature tip，记录每个 `head_sha`。
- 只在 checkpoint 更新依赖；不要持续把 integration merge 回每条分支制造不可审阅历史。
- 共享文件指定一个当前 owner。例如 layout/签名由 managed-abi 管，IL wrapper 由 browser-loader 管，编译模块 producer 由 jit-codegen 管。
- 合并冲突在拥有相关语义的功能分支解决并验证；integration 不积累没有归属的修复。
- 已测试 checkpoint 的 SHA 不改变；若 rebase/更新依赖，产生新 SHA 并重跑受影响门槛。

### 12.2 示例操作

foundation 通过当前门槛后：

~~~bash
git -C /work/wasm64/integration merge --no-ff wasm64/target-foundation

git -C /work/wasm64/runtime-source worktree add \
  -b wasm64/managed-abi \
  /work/wasm64/managed-abi \
  wasm64/integration
~~~

managed ABI 的接口 checkpoint 通过并入后，再从该固定 checkpoint 开 gc-memory、browser-loader、jit-codegen；callback-GC 等完整运行要求在联合 checkpoint 验证，不作为创建 GC 分支的前置条件。一个 feature branch 可以基于包含必要依赖的 integration checkpoint；它新增的提交应只做自己的功能，记录相对于该 checkpoint 的 diff。

计划中 integration 用于开发联合验证。面向 upstream 的 review branch 应在依赖已合入 upstream 后，rebase/cherry-pick 自己拥有的提交到新的 upstream base，再独立验证。维护者若接受 stacked PR，也应明确 base、依赖链接和实际 commit range。

**不要把 integration 的完整累积历史直接作为一个 PR。**

### 12.3 更新 upstream

准备阶段先固定本文 SHA。实现期间按可交付 checkpoint 检查 upstream 变化；不要在各分支正在联合调试时分别追最新 main。

若 upstream 已改变 Wasm ABI、helpers、loader 或测试框架，先在独立更新 checkpoint 评估，再整体更新相关分支。新基线的 wasm32 结果也应重建。外部工具链 patch 和 SDK SHA 分别记录。

### 12.4 每个 PR 的最低说明

- 解决哪个具体功能缺口、改变哪些可观察行为。
- 所依赖的已合入/在审变更。
- wasm32 与 wasm64 的实际验证范围。
- 对应 native/compiler/browser/package 证据。
- 当前仍未支持的能力；注明 baseline failure、skip 或资源阻塞。
- 新的 contract/format/ABI 决策及相关维护者讨论。

## 13. 结果记录标准

每次运行使用独立目录，例如：

~~~text
evidence/<source-sha>/<lane>/<run-id>/
  manifest.json
  commands.txt
  build.binlog
  stdout.log
  stderr.log
  test-results/
  module-inspection.txt
  native-link-inputs/
  measurements.json
~~~

上面是本计划建议的证据目录，不是声称现有 runner 会自动生成的结构。由执行者整理已有产物；不要为了记录结果改动生产功能。

manifest 至少记录：

- upstream base SHA、当前 feature/integration SHA、dirty 状态。
- repo/SDK/toolchain/browser/Node 的版本和实际路径。
- TargetOS、TargetArchitecture、RID、runtime/library/host/tasks configuration。
- 选中的 CoreLib、Crossgen2、native runtime、CORE_ROOT、runtime/compiler packs。
- 完整命令与相关、明确列出的环境变量；不要无差别导出整个凭据环境。
- discovered/executed/passed/failed/skipped 数量及 skip reasons。
- native 是否实际链接执行，R2R 是否有 compiled-body 证据。
- 高地址实值、memory size、seed、iterations、limit、peak memory、运行时间。

运行记录状态只采用：

- **PASS：**要求的断言确实执行且通过。
- **FAIL：**功能/回归断言失败。
- **BLOCKED：**环境或前置能力不足。
- **NOT RUN：**没有执行。
- **NOT APPLICABLE：**根据已声明支持范围不适用，附原因。

零测试、全 skip、打印 help 后返回成功、没有 memory64 能力，都不能算 PASS。整个 Interop suite 的汇总数字不能代替 native ABI 专项。任何未经执行的命令只能标为“源码核对”。

用 `tee` 保存输出时开启 `set -o pipefail`，不要让最后一个管道命令掩盖失败。需要 MSBuild binlog 的构建可使用仓库支持的 binary log 参数；每一步结束及时归档，避免后续构建覆盖相同默认日志文件。

## 14. 给远程执行者的首批指令

下面这段可直接作为准备阶段任务说明：

> 以 dotnet/runtime commit 2b5ea9af2991abe307beb855729ab52409d6333f 为基线，按《CoreCLR wasm64 云端实施计划》准备 Linux x64 环境。先创建 detached upstream-baseline worktree、wasm64/integration 与 wasm64/target-foundation；暂不同时创建其余功能分支。
>
> 验证磁盘、实际内存/cgroup 限制、native build dependencies；使用该 checkout 的 SDK、Emscripten 和 browser provisioning。记录实际 Node/Chrome 路径、版本和所需 Wasm features。
>
> 首先执行计划第 8 节的 wasm32 Release 产品构建、runtime 小测试、helper regeneration、真实 browser JS 测试，以及 packages 准备后的 workload smoke。分别记录各项结果；parser/compiler-only tests 与实际应用执行分开标注。失败时保留日志并缩小到环境或 upstream baseline 问题。
>
> 建立 evidence 目录和工具/源码 manifest。不要修改实验分支来替代基线，不要用 wasm32 产物冒充 wasm64，不要把 skip/zero tests/CLI help 当通过。
>
> 输出准备报告：已完成环境、实际通过的基线、失败或资源阻塞、工具链 micro-probe 结果、下一步 target-foundation 的具体文件与待解决合同。准备完成后按计划的分支依赖推进；每个功能的测试随功能提交，集成分支仅汇合通过当前阶段验收的 commits。

如果要让远程执行者一次领取整个实现任务，再补充：

> 后续沿 9 条功能分支推进，必要时开启 dotnet/sdk 的 wasm64/target-resolution。最多并行 2–3 条功能分支，默认同机只跑一个重型构建。遵循各阶段 gate，自主完成常规实现和定位；遇到真正影响公共合同的决策，提交具体差异、实验结果与推荐方案。完成时交付源码 commits、可复现 runbook、证据与剩余范围；GitHub 评论和上游 PR 的公开发送由另行指令决定。

## 15. 完成标准

“当前阶段完成”必须对应阶段的实际证据。整个主计划完成时，应同时满足：

1. 从干净源码可以选择和构建一致的 wasm64 target，工具链/native dependencies 可复现。
2. 普通 browser interpreter 路径、native ABI、GC/EH、实际高地址、growth 通过。
3. 共享 JS ABI 与真实 imports/exports 通过。
4. R2R 的编译与真实执行分别通过，包含混合调用与 GC/EH。
5. 新打包、安装的 SDK/workload 可以 build/publish/relink 并运行应用。
6. wasm32 以及被修改共享代码的相关 targets 无新增回归。
7. CI/runbook/结果记录能够重复上述判断，未测与未支持部分清楚可见。

## 参考源码

链接固定到本计划检查的 commit；实现时若更换 baseline，应更新对应记录。

- [构建入口及架构解析][build-script]
- [Linux dependencies][linux-requirements]、[SDK pin][global-json]、[Emscripten pin][emscripten-pin]
- [Wasm shared tool cache][tool-cache]、[browser provisioning][browser-provision]
- [CoreCLR browser runtime tests CI][runtime-ci]
- [runtime test runner][runtime-run]、[interpreter mode 定义][interp-config]
- [portable helper regeneration][helper-doc]、[Crossgen2 helper mode][crossgen-program]
- [构建子集][subsets]、[CoreCLR package dependencies][coreclr-packages]
- [browser app / native relink targets][browser-targets]、[native Wasm defaults][native-wasm]
- [IL WebCIL wrapper][webcil-wrapper]、[Wasm GC reservation][gc-wasm]
- [native test corerun][native-testkit]、[Interop wrapper 限制][interop-wrapper]、[corerun 配置][corerun-cmake]
- [JS interop tests][js-test-project]、[browser test runner][browser-tests]
- [Wasm.Build.Tests 模式与过滤][wbt-project]
- [R2R compiler tests][r2r-tests]、[实际 transition test][transition-test]、[方法执行证据说明][r2r-execution-evidence]
- [SDK R2R target resolution][sdk-resolver]、[JIT/EE interface 更新规则][jit-interface]
- [host managed-tools 测试][managed-tools-tests]、[SDK run-tests 指引][sdk-test-skill]、[SDK resolver tests][sdk-resolver-tests]、[SDK publish tests][sdk-publish-tests]
- [Memory64 规范说明][memory64-spec]、[Emscripten settings][emscripten-settings]
- [Memory64 issue #94108](https://github.com/dotnet/runtime/issues/94108)、[CoreCLR Wasm epic #134337](https://github.com/dotnet/runtime/issues/134337)

[build-script]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/build.sh
[linux-requirements]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/docs/workflow/requirements/linux-requirements.md
[global-json]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/global.json
[emscripten-pin]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/mono/browser/emscripten-version.txt
[tool-cache]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/wasm/WasmToolCache.props
[browser-provision]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/testing/wasm-provisioning.targets
[runtime-ci]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/pipelines/common/templates/browser-wasm-coreclr-runtime-tests.yml
[runtime-run]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/tests/run.sh
[interp-config]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/interpreter/interpconfigvalues.h
[helper-doc]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/vm/wasm/generate-coreclr-helpers.md
[crossgen-program]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/tools/aot/crossgen2/Program.cs
[subsets]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/Subsets.props
[coreclr-packages]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/.nuget/coreclr-packages.proj
[browser-targets]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/mono/browser/build/BrowserWasmApp.CoreCLR.targets
[native-wasm]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/native.wasm.targets
[webcil-wrapper]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/tasks/Microsoft.NET.WebAssembly.Webcil/WebcilWasmWrapper.cs
[gc-wasm]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/gc/wasm/gcenv.cpp
[native-testkit]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/tests/Common/CLRTest.WasmCorerun.targets
[interop-wrapper]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/tests/Interop/Interop.csproj
[corerun-cmake]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/hosts/corerun/CMakeLists.txt
[js-test-project]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/libraries/System.Runtime.InteropServices.JavaScript/tests/System.Runtime.InteropServices.JavaScript.UnitTests/System.Runtime.InteropServices.JavaScript.Tests.csproj
[browser-tests]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/eng/testing/tests.browser.targets
[wbt-project]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/mono/wasm/Wasm.Build.Tests/Wasm.Build.Tests.csproj
[r2r-tests]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/coreclr/tools/aot/ILCompiler.ReadyToRun.Tests/ILCompiler.ReadyToRun.Tests.csproj
[transition-test]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/src/tests/readytorun/wasm/WasmInterpreterTransitions/WasmInterpreterTransitions.csproj
[r2r-execution-evidence]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/docs/workflow/building/coreclr/wasi-r2r.md
[sdk-resolver]: https://github.com/dotnet/sdk/blob/5947e1a3ccd91c77991df85a763292e109ef4cc2/src/Tasks/Microsoft.NET.Build.Tasks/ResolveReadyToRunCompilers.cs
[jit-interface]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/docs/project/updating-jitinterface.md
[memory64-spec]: https://github.com/WebAssembly/memory64/blob/main/proposals/memory64/Overview.md
[emscripten-settings]: https://emscripten.org/docs/tools_reference/settings_reference.html
[managed-tools-tests]: https://github.com/dotnet/runtime/blob/2b5ea9af2991abe307beb855729ab52409d6333f/docs/workflow/testing/testing-managed-tools.md
[sdk-test-skill]: https://github.com/dotnet/sdk/blob/5947e1a3ccd91c77991df85a763292e109ef4cc2/.github/skills/run-tests/SKILL.md
[sdk-resolver-tests]: https://github.com/dotnet/sdk/blob/5947e1a3ccd91c77991df85a763292e109ef4cc2/test/Microsoft.NET.Build.Tasks.Tests/GivenAResolveReadyToRunCompilers.cs
[sdk-publish-tests]: https://github.com/dotnet/sdk/blob/5947e1a3ccd91c77991df85a763292e109ef4cc2/test/Microsoft.NET.Publish.Tests/GivenThatWeWantToPublishReadyToRun.cs


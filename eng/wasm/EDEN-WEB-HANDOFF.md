# UnrealSharp / UE Web 换机交接（2026-11-17）

任务暂停于换机交接。此文件记录已完成的实现与真实验证，不表示 UE Web 已验收。
主线目标：UnrealSharp 支持 UE Web，在 runtime wasm64 正向与 UnrealSharp 反向接通。

## 分支与依赖

远端为 `https://github.com/Edenlia/runtime.git`，均使用普通 push，不改写已发布历史。

| 分支 | 本次实现冻结点（交接提交之前） | 用途 |
| --- | --- | --- |
| wasm64/eden-main | abae5bf8332b0b4d1b5980a8290682aec42650d4 | wasm64 固有指针/宿主 ABI、WebCIL 修复 |
| test/eden-web-build-host | 5eb2d82b3bf8a23d7b8c116f461f51999b0c8ffe | Windows 本机构建、MSYS2 ICU、路径/cache |
| test/eden-web-native-pthreads | b86f292eafc1affd46e90b37abc380ad6e0d68a9 | 原生 pthread 兼容，仍是单 managed 线程 |
| test/eden-web-js-eh | 1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791 | **继续 UE 集成时使用此分支**，匹配 UE JS-SjLj |

host 从 intrinsic 的 ef532fc54eb 继续，67e37f25af2/abae5bf8332 分别以
4232340ecaa/1d7e7b280b8 采用；不是四条分支 HEAD 的简单线性继承。
native-pthreads 基于 host 5eb2d82b3bf；JS-EH 基于 native-pthreads b86f292eafc。
这些超出 wasm64 指针宽度的工作保持独立分支，未整批合入 wasm64/eden-main。

消费端：`https://github.com/Edenlia/UnrealSharp.git` 的
`test/eden-web-support`，实现冻结点 861a04521bf36a912340369033fd9359a2290aad，
从 test/eden-embedded-coreclr 的 8b64481c0c7dde3804e9e1911ba597c7eb797fad 创建。
完整下一步见该分支 `Docs/WebSupportHandoff.md`。

## 已验证与边界

- Windows 本机正常构建已跑通，无需 WSL；不能再沿用早期“只能 Linux 构建”的结论。
- JS-EH 的正常 clr.runtime+clr.hosts+clr.corelib+libs.native+host.native、libs.sfx、
  匹配 helper 生成器三次实际执行均退出 0。框架 180 DLL。
- JS-EH CoreLib SHA256：
  `c776057cf6c7407340cadbd59584107c1740901b11c325c2c61a5adab493b6db`。
- 独立真实 CoreCLR guest：Node 与 Chrome 的 Native64 和 UeLowered 四条均成功。
  Native64 最终 shared memory/table64；UeLowered 经 MEMORY64=2 降为 shared
  memory/table32，两者 C/C++ 指针和函数指针仍为 8 字节。
- 真正 initialize/create_delegate、PInvoke/UCO（45/-33、2 次 native callback）、
  typed catch / throw-from-catch / rethrow / finally / filter（flags31）、
  owner-thread shutdown 与实际 onExit(0) 通过。
- 真实 UE 5.9 Preview：JS-EH 产品的 **最终 UE JavaScript 链接与 cook 通过**。
  正常 BCR 在 stage 被 Zen 生命周期/本机 IPv6 代理阻塞；未完成 package/archive、
  UE 浏览器 C# Actor、正常 UE 退出后 CLR Closed 验收。
- JS-EH 是默认关闭的 interpreter / direct IL PE / native-pthread-compatible /
  单 managed 线程 profile。没有承诺 R2R、WebCIL、managed threading、任意 async/
  JSInterop、>4GiB 分配或完整性能验收。C++ 异常必须处理在 runtime 自己的帧内，
  不能依赖穿越 UE 已有 -fignore-exceptions 帧。

## 环境与换机

- UE 使用 Installed UE 5.9 Preview（本机目录 UE_5.9，CL60351404），保持正常
  Game/Wasm/Development/wasm64 设置。UE 实际默认 MEMORY64=2；
  wasm64 指针 ABI 不意味着浏览器最终 memory64。
- Emscripten **6.0.10**；UE 使用 SDK 原装编译器。runtime 内联汇编需要该 LLVM
  同源版本的 table64 assembler checker 修复，构建时仅进程局部 EM_LLVM_ROOT。
  不要替换 UE SDK 的直接编译器。
- 实测 runtime 修复版 clang SHA256：
  `6c5ce14d830a38be10991a4d639a881b32d6399e3d59717cf8f9d3ce732590a4`；
  UE 原装 clang SHA256：
  `df2dbb7a2c15af615ef7408a70d4245007cfef602af60fb676aeb6c55e83354c`。
  修复版来自 SDK LLVM 基线 a06d916 + table64 checker 修复；这些 LLVM 二进制不在 Git。
  精确源码/构建记录需从旧机 Toolchain 证据目录迁移，或在新机重建并重新验证。
- runtime 固定 SDK 为 .NET 12.0.100-alpha.1.26557.102；
  UE 使用其内置 .NET 10，Game 为 net10.0 普通 IL。不要混用 CoreLib/framework/helpers。
- ICU72.1 recipe9，MSYS2 Windows host、native pthread、ICU 自身无 C++ 异常。
  支持验证并复用真正 fingerprint 匹配的外部 ICU。不要改写其原生产者身份。
- 使用独立 worktree、输出和 EM_CACHE/EM_CONFIG；正常 eng/build.ps1 流程。
  native job2、MSBuild /m:1 是本次 runtime 执行设置；UE 不增加便捷编译 flags。
- 旧机器证据根（仅本地，非 Git 产品）：
  `<UnrealEngine>/CentralParkProjs/.cache/UnrealSharp/Operations/ue-web-support/20261116`。
  详见 `plan.md`、`work-log.md`、`RuntimeHost/JsEh/README.md`、
  `RuntimeHost/JsEh/Guest/DirectPeGuest-1e9f8bd1/results.json`。
  results.json SHA256：
  `a0cee1c5c6bb1489b255a074b28ac4f6bb73c48ec4e2fd09552846f8606c66eb`。
- JS-EH 分支的 `eng/wasm/handoff/` 保存 guest 源码及当时驱动参考。
  参考脚本含原机器路径，迁移时重配根目录、工具与新输出，并重新执行产生新证据。
  旧 receipts 只能证明旧产物。交接文档提交会改变 HEAD；旧产品的 emitted Git stamp
  仍是 1e9f8bd1，不能改写成后来的文档提交。若按新 HEAD 重建，应生成新产品/key。

## 精确续接点

先阅读 UnrealSharp 的交接文档并恢复/重建 JS-EH RuntimeProduct。
下一次应新建完整正常 BCR case04：
保持正常 Zen sponsor 跨 cook→stage 生命周期，并在启动 UAT 的那个进程局部
保留现有 NO_PROXY 后追加 **[::1]**。
实测相同活 Zen、同 UE .NET：默认 HttpClient 502、禁代理 200、
仅子进程 NO_PROXY 加 [::1] 后默认 HttpClient 200。
第三次包装尝试在已有 Zen 保护检查处中止，**没有启动 UAT**，不是上述修正已验收。
不要停用户 Editor/Zen/proxy，也不要手改 ue.projectstore 或全局代理配置。

## 本分支职责与本地重建

1e9f8bd1e90 是单个 owning feature（14 files），详情见
[JS-EH profile](README-coreclr-browser-js-eh.md)。
旧尝试 844e6c71（私有 Frame::Next）和 11f809be（JS footer 裸预处理）
均已修正；最终正常全图与四条 guest 重新执行成功。

`handoff/` 包含实际使用的 guest 源码、原始驱动参考和证据摘要，
不包含 binaries/caches。入口见 [handoff README](handoff/README.md)。

正常重建顺序：
1. provision 固定工具链、独立缓存、验证/构建 ICU recipe9；
2. 正常 eng/build.ps1 的 clr.runtime+clr.hosts+clr.corelib+libs.native+host.native；
3. 相同 profile/路径正常 libs.sfx；
4. 匹配 ILCompiler.ReadyToRun/HelperHost（仅生成 helper，不是把 guest 改成 R2R）；
5. 生成全部三份 helper，正常 CMake guest，Node+Chrome 两种最终内存模型；
6. 基于实际完成产物 capture/export/verify RuntimeProduct，然后交 UnrealSharp。

核心 properties 为 CoreClrBrowserJsEh=true、WasmNativePthreads=true，
以及固定 BuildSubdirectory=native-pthreads 和实际 CoreclrRuntimeBinDir/
CoreCLRArtifactsPath；详见参考 driver，别让部分子图回落到另一个 profile。
此前全图 9m27.61、libs.sfx 5m23.70 均0 warnings/errors，不保证新机器耗时相同。

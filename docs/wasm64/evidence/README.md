# 归档证据

此处保存13份原始JSON记录及其 [SHA256清单](inventory.json)，逐字节拷贝自实际运行记录。
总览见 [validation.md](../validation.md)。这些是历史结果，不是可执行测试，也不接入CI。

- `a-` / `b-` / `c-`：各独立分支的被测输入与结果；`b-existing128-amend.json` 是删掉专项测试后的128项结果。
- `d-native-` / `d-asm-`：全新D Release producer、产品检查、实际汇编对照。
- `llvm-user-`：实际MC的源码/补丁/二进制身份及独立复核。
- `historical-validation-matrix.json`：删除专项测试前的四分支矩阵，旧SHA与旧测试数量保持原样。
- `history-rewrite.json` / `independent-final-audit.json`：旧→新SHA、生产代码不变及测试清理/拓扑检查。
- `four-branch-push-verification.json`：上一次四分支force-with-lease后的远端核对，不是eden-main推送结果。

记录内的绝对路径、旧的not pushed状态、旧测试文件路径及源码repo路径属于当时环境快照，不能作为当前文件存在或当前执行状态的保证。历史路径不作为文档链接检查目标。
原始binlog/TRX/二进制、SDK/cache及完整构建目录未放入Git；其hash/历史位置按receipt记录，本归档不保证这些外部文件永久可下载。重新复现需要独立获取声明的工具链和输入，重新运行现有产品/测试入口。

不恢复已删除的专项harness或实验adapter。当前分支状态以status.json及Git为准，不对历史JSON重写SHA或把未执行结果标成PASS。

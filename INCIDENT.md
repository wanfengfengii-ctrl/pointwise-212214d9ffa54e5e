# 北坡口误更正事故：根因与实测记录

## 事故经过

晨场发行含两句：C「标本采自北坡」、D「请触摸模型边缘」。甲、乙两席各领到 C 后，
领讲人发现口误并提交更正 M：正确词「标本采自南坡」、勘误词「更正，刚才的北坡应为南坡」。
此时甲已实播 C 但回包丢失，乙的 C 播放请求被扣留未发。

按 README 约定，正确结局应为：甲保留原播并补一次勘误；乙只播正确词；
乙迟到的旧凭据不得首次播出；查实后按席显示结局与原播、更正序号；收场按各席实播顺序签存。

## 根因

四处缺陷，全部在更正交办路径上：

1. `seats/execution.py` `accept_seat_instruction`：席已实播原句时直接返回
   `AmendmentAcceptance(None, None)`，拒发更正凭据。甲拿不到 `play_token`，
   更正单永远 `pending`，收场永远 `pending`。
2. `release/amendments.py` `_notice`：更正词类按**全场**是否存在该句派发记录统一定夺，
   且全场只发一种词。领取即产生派发，故未实播的乙也被发了勘误词，而非只播正确词。
   词类应按**本席实播事实**定夺：已实播→勘误，未实播→替换。
3. `seats/execution.py` `play`：缺少旧凭据失效检查。更正在本席受理后，迟到的或
   后来领取的原句凭据仍能首次实播，违反「先受理则旧凭据失去首次实播资格」。
4. `release/amendments.py` `record_seat_evidence`：查实证据硬编码
   `'original_seq': None`，勘误席的结局丢失原播序号。

## 修复

- `seats/execution.py`：`AmendmentInstruction` 改载正确词与勘误词两文；
  `accept_seat_instruction` 按本席 `find_original` 结果定词类（已实播→erratum、
  未实播→replacement），一律签发本席更正凭据；重投时读回已存凭据的词类、
  实播回执与原播序号。`AmendmentAcceptance` 增加 `kind` 与 `original_seq`。
- `seats/execution.py` `play`：原句凭据首次实播前检查本席是否已受理该句更正，
  已受理则拒绝并返回 409 `stale_original`；已实播的原凭据仍走原号回执复领。
- `seats/queue.py`：新增 `has_amendment_command`，在席库凭据中定位该句更正凭据。
- `release/amendments.py`：删除按场定词类的 `_notice` 与 `amendment_notices` 表
  （词类由席端实播事实决定且受理后不变）；`amend` 用更正单存根构建交办；
  `record_seat_evidence` 按席端受理结果记录 `original_seq` 与 `amendment_seq`。

## 实测

修复前（`git stash` 可复现基线 114149b）：

- `python3 -B check_project.py`：20 项中 6 项失败
  （test_amendment 4 项、test_closeout 2 项）。
- `python3 -B incident.py`：退出 1，`MUSEUM_CORRECTION_DIVERGED`。实测
  甲更正凭据为 `null`（补播无果）、乙播出勘误词而非正确词、乙迟到旧凭据
  以 200 首次实播、甲结局永远 `pending`、收场 409 `pending`。

修复后：

- `python3 -B check_project.py`：21 项全部通过（原 20 项 + 新增回归
  `tests/test_correction_incident.py`，把事故时间线固化进回归套件）。
- `python3 -B incident.py`：退出 0，实测与预期逐项一致：
  - 甲：`[1, original, 标本采自北坡]`、`[2, erratum, 更正，刚才的北坡应为南坡]`、
    `[3, original, 请触摸模型边缘]`；结局 `erratum_played`，原播序 1、更正序 2。
  - 乙：迟到旧凭据 409 `stale_original`；`[1, replacement, 标本采自南坡]`、
    `[2, original, 请触摸模型边缘]`；结局 `replacement_played`，无原播序、更正序 1。
  - 收场 200 `closed`，报告按各席实播顺序保留内容与出处。
- `python3 -B -m routing.http_api demo` 与 `python3 -B incident.py --demo`：
  退出 0；演示场甲 `erratum_played (1, 3)`、乙 `replacement_played (None, 2)`。
- `run_api.py` 指定数据目录重启：仅补齐缺失结构，稿件修订保留（修订号续增）。

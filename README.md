# 社区科学馆无障碍讲解服务

馆方编排表给出有名讲词、声道和拍长。讲解员先校样，再把通过的讲稿修订固定为一场发行。启用席上的志愿者独立领播。发生口误时，领讲人提交正确词和勘误词。收场报告供领讲人核对各席实际听到的内容。

## 运行

使用 Python 3.11 标准库。以下命令在项目根目录运行。

```sh
python3 -B check_project.py
python3 -B -m routing.http_api demo
python3 -B -m routing.http_api serve --data-dir ./session-data --port 8765
```

服务仅监听 `127.0.0.1`。演示从 `samples/day.json` 读取编排和更正，使用临时库及系统分配的环回端口，经过真实 HTTP 请求输出查单和固定报告。校样以整数拍计数。同声道的 `[start, start + duration)` 可以接边。讲词保留输入原文，冻结句序取原提交列表位次。实时记录按每席独立递增的实播序，允许实际播出顺序与原稿不同。

指定数据目录再次启动只补齐缺少的存储结构。稿件修订、冻结发行、首执和签存记录保留。演示样例由 demo 显式提交，正常服务启动时不载入样例。

`python3 -B incident.py` 用临时数据目录回放北坡口误，打印两席的实播、查单与收场对照，业务结果不符时退出失败。加 `--demo` 可展示同一对照。

`.pointwise-runtime.json` 使用版本 1 的 API 清单。`setup` 可列准备命令，本服务为空。`start`、`verify` 和 `demo` 各写一条 argv。启动入口接受 `${POINTWISE_HOST}` 和 `${POINTWISE_PORT}`，只绑定环回地址，初始化完成后在 `readiness_path` 指定的 `/health` 响应。核验运行原回归，演示展示事故请求的实测结果。

## JSON HTTP

POST 接受 JSON 对象。GET 参数放在查询串中并做 URL 编码。除 `proof` 的 `cues` 校验外，列出的入参均为必填，未知字段拒绝。

| 入口 | 入参 | 结果 |
| --- | --- | --- |
| `POST /proof` | `draft_id, cues`。每句含 `cue_id, channel, start, duration, text` | 登记该稿的新整数修订，返回 `revision, passed, intervals, conflicts, field_errors`。起拍非负，拍长为正，两者须为 JSON 整数。区间含 `cue_id, channel, position, start, end`。冲突含 `channel, first, second`。 |
| `POST /publish` | `draft_id, revision, show_id, seats` | 冻结这份通过校样的准确修订，返回发行号、场次、启用席与冻结句。`seats` 为非空且不重复的文本列表。 |
| `POST /claim` | `show_id, seat, request_id` | 推进本席领取位次，返回 `command`。取完后返回 `command: null`。同号复领原命令，命令含 `token, text, origin` 等字段。 |
| `POST /play` | `show_id, seat, token, request_id` | 返回 `request_id, playback`，其中 `playback` 含本席 `seq`、原句出处、实播词和 `kind`。 |
| `POST /amend` | `show_id, amendment_id, cue_id, corrected_text, erratum_text` | 登记并向启用席交办，或用同参续办及核回已产生的实播证据。返回当前更正单。 |
| `GET /amend_status` | `show_id, amendment_id` | 返回已记录的更正单与逐席结局。读取无副作用。 |
| `POST /close` | `show_id, request_id` | 齐备时签存并返回 `status: closed` 与 `report_id`。证据不足时返回 HTTP 409、`status: pending` 及 `pending` 明细，同号可重试。 |
| `GET /report` | `report_id` | 读回固定 `show_id, report_id, seats`，各席内容按该席实际播放顺序排列。 |

### 领播、口误和收场

每次领取固定派发出处。`origin` 含 `edition_id, draft_id, revision, cue_id, position`。即使原句更正，原领取号仍返回原凭据。志愿者从更正单的本席 `play_token` 领取更正播放凭据。该凭据与普通播放用同一个 `/play` 入口。更正在本席先行受理时，任何原句凭据均失去首次实播资格，包括稍后从固定发行取得的原句凭据。此前已经实播的原凭据仍可用原播放号复领首执。

更正单的 `seats` 映射按开场名单返回各席。`pending` 表示仍待核实，两个实播序均为空，席端受理后才有 `play_token`。播出更正后，重投同参 `/amend` 核回实播，已核实项显示 `replacement_played` 或 `erratum_played`，并给出 `original_seq` 和 `amendment_seq`。替换没有原实播序。席端不可达时，该席仍可用原号续办。未涉更正的句照常领播。一场内的一句只允许一张更正单。

领取号和收场号各自在控制端的对应入口内唯一。播放号在本席内唯一，更正号在本场内唯一。同号同参复领或续办，异参返回 `request_mismatch`。成功收场后可复领已有结果，新收场号、领取号和更正单均不能改变已签场次。待核收场没有成功首执。`pending` 项给出席、句和待核理由。收场同时核对实际词、出处和实执。

字段格式错误返回 HTTP 400。可定位到稿号的校样驳回返回 HTTP 200 和 `passed: false`，区间冲突或字段问题见相应数组。未知对象返回 HTTP 404 及 `error`。未通过校样、重复开场、异参复用、旧凭据首次执行及已收场等冲突返回 HTTP 409 及 `error`。暂不可用的席库返回 HTTP 503，原号可重试。

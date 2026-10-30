# SES 发信模块（G9｜WP-E 预建）

模块已在 `server/src/fde_api/mailing/` 预建，**默认整体关闭**。SES 生产访问批复下来后**只需改配置启用**（见文末「启用清单」），无需改代码。

> 现状边界（不因本模块改变）：AWS 生产访问（Sending Limit Increase）尚未批复；收信仍是既有 Gmail（SES 无 IMAP/POP，收信必须另有邮箱通道）。本模块只管**发信**与**退信/投诉回调**。

## 一、模块结构

| 文件 | 职责 |
|---|---|
| `mailing/policy.py` | 纯逻辑闸门（G3 起）：开关 → 幂等 → 抑制 → 限额；四态分类；退避；发信域约束。零 AWS 依赖 |
| `mailing/ses_client.py` | SESv2 `SendEmail` 客户端 + `SesClient` 协议（测试用假实现）；boto3 **延迟导入**——未启用时不 import AWS 栈 |
| `mailing/service.py` | 发送编排（`send_email`）+ SNS 回调处理（`handle_sns_envelope`） |
| `mailing/routes.py` | 仅 `POST /api/v1/mailing/sns/events`（SNS 退信/投诉/订阅确认回调） |
| `mailing/models.py` | `mailing_sends`（发送台账）、`mailing_events`（反馈事件） |
| `migrations/…_mailing_tables.py` | 迁移 `a9c3f1d8e2b4`（两表，幂等键唯一） |

**发送路径不设 HTTP 路由**：`send_email` 是 service 函数，由 worker/n8n 桥接层调用——避免在 SES 未批复时出现一个可被打的发信口。

## 二、配置（只写变量名，值进 `server/.env`）

| 变量 | 含义 | 默认 |
|---|---|---|
| `FDE_SES_ENABLED` | 模块总开关 | `false`（关闭） |
| `FDE_SES_REGION` | SES 区域 | `us-east-1` |
| `FDE_SES_SEND_SUBDOMAIN` | 允许发信的**子域根**（如 `mail.somwyn.com`） | 空 |
| `FDE_SES_FROM_ADDRESS` | 发件地址（须落在上面子域内） | 空 |
| `FDE_SES_REPLY_TO_ADDRESS` | 可选 Reply-To | 空 |
| `FDE_SES_TOPIC_ARN` | SNS 事件主题 ARN（回调端点的来源白名单） | 空 |
| `FDE_SES_DAILY_LIMIT` | 每日发送上限（沙盒口径） | `10` |
| `FDE_SES_CONFIGURATION_SET` | 可选：SES 配置集（事件路由到 SNS 用） | 空 |

启动即校验：`FDE_SES_ENABLED=true` 时必须同时给全子域/FROM/TopicArn，且 FROM 的域必须落在允许子域内（主域 `somwyn.com` 直接启动失败——`ses_sender_domain_forbidden`）。

AWS 凭证：**不配进本模块**。boto3 走默认凭证链（容器内 IAM role 或标准 `AWS_*` 环境变量）。密钥入 VCS 是红线，任何 AWS key 都不进仓库。

## 三、发信域与 DKIM（写文档，不写死代码）

项目口径：**主域 `somwyn.com` 不发信，只用子域**（如 `mail.somwyn.com`）。该口径在代码（`policy.is_allowed_sender_domain` + 配置校验器）与 DNS 两处都要落实：

### 3.1 DKIM（子域）

- SES 控制台 → 身份验证 → Easy DKIM：生成 3 条 CNAME，**挂在 `mail.somwyn.com`**（不是主域）。
- Cloudflare 加这 3 条 CNAME：**DNS only（灰云）**，不要代理。
- 记录值形如 `xxxx._domainkey.mail.somwyn.com` → `xxxx.dkim.amazonses.com`（以 SES 控制台实际给出为准）。

### 3.2 SPF（关键一致性点）

- **子域** `mail.somwyn.com` 单独加 SPF：`v=spf1 include:amazonses.com ~all`。
- **主域 `somwyn.com` 的 SPF 不要加 `include:amazonses.com`**——主域不发信，把 SES 授权挂到主域等于把 SPF/DKIM 面扩大到主域全部邮件，与项目口径冲突。
- 已有主域 SPF 时保持原样，只在子域新增记录。

### 3.3 DMARC

- `\_dmarc.somwyn.com` 先 `p=none` 起步并收集报表，确认无误报后再收紧（收紧前要有几周干净报表）。
- 与主域 SPF 不加 SES include 的口径一致：DMARC 策略作用于主域，但对子域发信无影响。

### 3.4 沙盒

- 生产访问批复前是沙盒：每日 200 封上限，且**只能发给已验证收件人**。
- 模块内 `FDE_SES_DAILY_LIMIT` 默认 10 封/天，比沙盒更严——批次跑量前先调这个数（而非依赖 AWS 侧上限）。

## 四、事件回调（SNS）与服务主体策略

SES 配置集把退信/投诉/送达事件发布到 SNS 主题 → SNS 以 **HTTPS** 订阅推给工作台端点 `POST /api/v1/mailing/sns/events`。

### 4.1 SNS 主题策略（允许 SES 发布，必须带 SourceArn）

SES 是 `ses.amazonaws.com` 服务主体向 SNS 主题发布——**不带 `aws:SourceArn` 就是 confused-deputy 洞**（任何账号的 SES 都能往我们的主题里灌事件）。策略示例：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSesPublishOnly",
      "Effect": "Allow",
      "Principal": {"Service": "ses.amazonaws.com"},
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:<region>:<account-id>:<topic-name>",
      "Condition": {
        "StringEquals": {"aws:SourceAccount": "<account-id>"},
        "ArnLike": {"aws:SourceArn": "arn:aws:ses:<region>:<account-id>:configuration-set/<configuration-set-name>"}
      }
    }
  ]
}
```

（`aws:SourceArn` = SES 配置集 ARN；`aws:SourceAccount` 同样要写。）

### 4.2 工作台端的鉴权 = 签名，不是 JWT

SNS 推送不可能携带工作台 JWT。端点因此按 **SNS Signature v1** 校验：

- `SigningCertURL` 必须在 `sns.<region>.amazonaws.com` 域内（否则 403，且**不发起任何外联**）；
- 用证书公钥验签（RSA-SHA256，字段序按 AWS 固定顺序）；
- `TopicArn` 必须等于 `FDE_SES_TOPIC_ARN`（否则 403）；
- 订阅确认回访 `SubscribeURL` 同样限 `sns.*.amazonaws.com`（纵深防御）。

即便签名通过，端点也不信任 `Message` 内容里的任何字段作为指令——只解析成事件分类落库。

### 4.3 幂等与抑制

- SNS 是 at-least-once 投递 → 事件按 `event_key` 唯一（`{messageId}:{notificationType}:{recipient}`）落库，重放不重复计。
- **bounce / complaint = 地址级死刑**：该地址进抑制名单，后续发送直接 `drop_suppressed`。
- **delivery 不影响地址**；throttle 只记事件不抑制（调用方按可重试退避）。

## 五、发送闸门顺序（`policy.decide_send`，固定顺序可复现）

1. `drop_disabled` —— 开关未开（配置层已拦，这里再兜一层）。
2. 发信域约束 —— FROM 不在允许子域 → `drop_sender_domain_forbidden`。
3. `drop_duplicate` —— 同 `idempotency_key` 已发过（重试=同键新 attempt；同键二次请求不再打 SES）。
4. `drop_suppressed` —— 收件人有未消退的 bounce/complaint。
5. `drop_over_quota` —— 当日已发数达到 `FDE_SES_DAILY_LIMIT`（**只数当日**，UTC 日界）。
6. `send` —— 打 SESv2 `SendEmail`，落 `mailing_sends` 行（幂等键 + MessageId）。

失败分类：throttle → 503（可重试，按 `policy.next_retry_delay` 退避）；拒收/其他 → 502（不可重试）。失败**不占发送台账**（台账只记 SES 已接受的发送）。

## 六、数据留存口径

- `mailing_sends`：幂等键、SES MessageId、发件/收件地址、状态、发送时间。**不落邮件正文**。
- `mailing_events`：事件键、分类、细分类型（`bounceSubType` / `complaintFeedbackType`）、收件地址、原始 SNS Message 的 **sha256 指纹**——**不落通知原文**（退信诊断里可能带客户侧邮件内容）。
- 两表都不挂项目/用户外键：回调可能在业务行清理后到达，事实独立留存。

## 七、启用清单（批复后按序做）

1. AWS Support 申请 SES 生产访问（Sending Limit Increase）——**等批复，不空等**。
2. 在 SES 控制台验证发信域 `mail.somwyn.com`（Easy DKIM → 3 条 CNAME 落 Cloudflare 灰云）。
3. 子域加 SPF（主域**不动**）；主域加 DMARC `p=none`。
4. 建 SES 配置集 + 事件目标（SNS 主题），配置 SNS 主题策略（带 `aws:SourceArn` + `aws:SourceAccount`）。
5. SNS 主题加 HTTPS 订阅 → `https://<host>/api/v1/mailing/sns/events`；首次回访订阅确认后事件开始推送。
6. `server/.env` 填 `FDE_SES_ENABLED=true` + 子域/FROM/TopicArn/限额（**值只进 .env，不进仓库**）。
7. `docker compose build && docker compose up -d` + `alembic upgrade head`（新增两表迁移）。
8. 用沙盒收件人做一次端到端：发送 → SNS 回调 → `mailing_events` 落行 → 构造一次 bounce → 该地址进抑制。

## 八、测试覆盖（27 例，全 mock，零真实邮件）

`server/tests/test_mailing_ses.py`：

- 发送闸门 8 例（关闭/成功落账/幂等重复/抑制/超限/限额只数当日/主域拒绝/throttle 与拒收分类）；
- `BotoSesClient` 3 例（botocore **Stubber**，参数映射与错误分类，零网络）；
- SNS 回调 12 例（订阅确认回访、bounce/complaint/delivery、幂等重放、坏签名/非白名单证书/错主题/非法 JSON 全 403 或 400）；
- HTTP 路由 2 例（关闭态 403；**text/plain content-type** 的 SNS 报文可解析——SNS 实际就是这么发的）；
- 配置校验器 1 例（三项必填 + 主域 FROM 拒绝）。

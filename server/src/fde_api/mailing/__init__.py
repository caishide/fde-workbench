"""WP-E SES 发信模块（goal-r3 G9 预建，默认关闭）。

分层：policy（纯逻辑闸门，G3 起）→ ses_client（AWS 面，boto3 延迟导入）→
service（编排 + SNS 回调）→ routes（仅 SNS 回调端点）。

**默认整体禁用**：FDE_SES_ENABLED 未显式开启时，发送路径直接落
drop_disabled、SNS 回调端点一律 403——SES 生产批复下来只需改配置启用，
默认部署零行为影响、零 AWS 依赖（boto3 延迟导入，未启用时不 import）。

信任边界：SNS 回调不可能携带工作台 JWT，**签名即鉴权**——端点校验
Signature v1（RSA-SHA256）+ 签名证书必须来自 sns.*.amazonaws.com +
TopicArn 白名单。退信/投诉只落地址 + 分类 + 通知 sha256 指纹，不落通知原文。
"""

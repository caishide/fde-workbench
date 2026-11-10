"""多客户 M2：四入口统一注册与认证（任务书 §7-M2；ADR-M2/ADR-M4）。

部署闸 fail-closed（默认 404）；邮箱验证一次性令牌；注册状态机
pending_email → pending_review（审核制入口）→ active / suspended / rejected。
"""

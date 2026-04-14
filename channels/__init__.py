"""channels — Feishu IM and Web chat channel adapters.

Layer: L2 (application-specific).

Currently contains business-specific logic (CRM integration, business_mode,
admin commands) that couples it to autoservice. Classified as L2 until a
second application needs channel adapters, at which point the generic parts
(~40%: WebSocket routing, pub/sub bridge, message dispatch) should be
extracted to socialware/ as an L1 channel framework.

See CLAUDE.md "channels/ L1 extraction roadmap" for details.
"""

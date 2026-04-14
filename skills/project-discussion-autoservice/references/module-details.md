# AutoService Module Reference

> Auto-generated from `.artifacts/bootstrap/module-reports/*.json`
> Date: 2026-04-10

---

## Table of Contents

1. [autoservice](#autoservice) -- Core shared library
2. [feishu](#feishu) -- Feishu IM channel (MCP + WebSocket)
3. [web](#web) -- Web chat channel (FastAPI)
4. [plugins](#plugins) -- Customer-specific declarative plugins
5. [tests](#tests) -- Unit and E2E tests

---

### autoservice

**职责**：Core shared library providing config, database, session, permission, plugin loading, CRM, API client, and utility functions (`autoservice/__init__.py:21`)

**关键接口**：

| 接口 | 位置 | 说明 |
|------|------|------|
| `generate_id(name: str) -> str` | `autoservice/core.py:11` | Generate 8-char MD5-based unique ID from name and timestamp |
| `sanitize_name(name: str) -> str` | `autoservice/core.py:17` | Convert name to filesystem-safe format (alphanumeric, Chinese, hyphens; max 30 chars) |
| `ensure_dir(path: Path) -> Path` | `autoservice/core.py:30` | Ensure directory exists (mkdir -p) and return it |
| `load_config(config_path: Path) -> dict` | `autoservice/config.py:118` | Load configuration from a YAML file |
| `get_domain_config(domain, config_path, language) -> dict` | `autoservice/config.py:127` | Get domain configuration with language support; tries config file, then built-in defaults |
| `save_record(domain, record_type, data, config) -> Path` | `autoservice/database.py:30` | Save a record as info.json + README.md in a named subdirectory |
| `list_records(domain, item_type, verbose, config) -> dict` | `autoservice/database.py:86` | List records of specified type(s) from the filesystem database |
| `get_record(domain, record_type, name_or_id, config) -> tuple` | `autoservice/database.py:132` | Get a single record by name or ID (case-insensitive search) |
| `update_record(domain, record_type, name_or_id, updates, config) -> Optional[Path]` | `autoservice/database.py:171` | Update an existing record's fields; regenerates README.md |
| `delete_record(domain, record_type, name_or_id, config) -> bool` | `autoservice/database.py:226` | Delete a record directory using shutil.rmtree |
| `print_results(results, config, verbose)` | `autoservice/database.py:253` | Print list_records results in formatted output with domain-specific labels |
| `get_output_dir(domain, item_type, config) -> Path` | `autoservice/database.py:21` | Get output directory Path for a given domain and item_type |
| `extract_from_docx(file_path: Path) -> list[dict]` | `autoservice/importer.py:16` | Extract structured data from DOCX file; auto-installs python-docx |
| `extract_from_xlsx(file_path: Path) -> list[dict]` | `autoservice/importer.py:51` | Extract structured data from XLSX file; auto-installs openpyxl |
| `extract_from_pdf(file_path: Path) -> list[dict]` | `autoservice/importer.py:86` | Extract structured data from PDF file; auto-installs pdfplumber |
| `import_file(file_path, output_dir, item_type) -> list[Path]` | `autoservice/importer.py:149` | Import data from DOCX/PDF/XLSX and save items to output directory |
| `import_to_domain(domain, file_path, item_type, config) -> list[Path]` | `autoservice/importer.py:186` | Import data from a file into a specific domain's database directory |
| `init_session(domain, config) -> tuple[str, Path]` | `autoservice/session.py:122` | Initialize a session: detect Claude session ID, generate name, create directory |
| `generate_session_id(domain, claude_session_id, config) -> str` | `autoservice/session.py:149` | Generate session ID in format {prefix}_{YYYYMMDD}_{seq}_{claude_session_id} |
| `get_claude_session_id() -> str` | `autoservice/session.py:23` | Auto-detect current Claude Code session ID by walking the process tree |
| `save_session(domain, session_id, product, customer, operator, conversation, review, config) -> Path` | `autoservice/session.py:201` | Save a complete session with conversation and review as session.json + README.md |
| `APIClient(domain, base_url, timeout)` | `autoservice/api_client.py:19` | HTTP client for AutoService API calls; reads mock server info or uses provided base URL |
| `APIClient.query_customer(identifier)` | `autoservice/api_client.py:72` | GET /api/v1/customers/{identifier} |
| `APIClient.query_subscriptions(customer_id, service_name)` | `autoservice/api_client.py:75` | GET customer subscriptions, optionally filtered by service_name |
| `APIClient.query_billing(customer_id, start_date, end_date)` | `autoservice/api_client.py:80` | GET customer billing with optional date range |
| `APIClient.query_purchases(customer_id)` | `autoservice/api_client.py:85` | GET customer purchase history |
| `APIClient.query_order(order_id)` | `autoservice/api_client.py:88` | GET order by order_id |
| `APIClient.query_pricing(product_id, tier, user_count)` | `autoservice/api_client.py:91` | GET product pricing with optional tier and user_count |
| `APIClient.query_feature(product_id, feature_name)` | `autoservice/api_client.py:96` | GET product feature availability |
| `APIClient.query_services(category)` | `autoservice/api_client.py:99` | GET available services by category |
| `APIClient.check_permission(action, product_id)` | `autoservice/api_client.py:102` | POST permission check for an action on a product |
| `APIClient.request_refund(customer_id, order_id, reason, amount)` | `autoservice/api_client.py:109` | POST refund request |
| `APIClient.change_subscription(customer_id, subscription_id, action)` | `autoservice/api_client.py:117` | PUT subscription change (cancel, upgrade, etc.) |
| `format_api_response(response, endpoint, language) -> str` | `autoservice/api_client.py:127` | Format API response dict for conversation display (zh/en) |
| `format_permission_response(response, language) -> str` | `autoservice/api_client.py:165` | Format permission check response for conversation display (zh/en) |
| `APIResponse` (dataclass) | `autoservice/api_interfaces.py:14` | Standardized API response container with success, data, endpoint, is_mock fields |
| `APIResponse.to_display_block()` | `autoservice/api_interfaces.py:23` | Format response as Chinese-language display block |
| `APIInterface` (dataclass) | `autoservice/api_interfaces.py:44` | Definition of a system API interface with name, description, endpoint, method, params |
| `APIQueryEngine(mode, base_url)` | `autoservice/api_interfaces.py:76` | Engine for executing API queries; builds prompts for mock data or executes real HTTP requests |
| `APIQueryEngine.build_query_prompt(interface, params, customer) -> str` | `autoservice/api_interfaces.py:87` | Build a Chinese-language prompt for Claude to generate mock API response data |
| `get_interface(name, product_interfaces) -> Optional[APIInterface]` | `autoservice/api_interfaces.py:216` | Get API interface by name; checks product-specific then COMMON_INTERFACES |
| `query(prompt, cwd) -> AsyncIterator[Any]` | `autoservice/claude.py:13` | Execute a Claude Agent SDK query with proxy-aware env; yields raw message objects |
| `PermissionLevel` (enum) | `autoservice/permission.py:15` | 4 levels: APPROVE_IMMEDIATELY, REQUIRES_SUPERVISOR, REQUIRES_PROCESS, FORBIDDEN |
| `PermissionCheck` (dataclass) | `autoservice/permission.py:24` | Result of a permission check with action, level, allowed, reason, workflow, conditions |
| `OperatorPermissions(rules)` | `autoservice/permission.py:60` | Permission configuration with four rule lists; check_permission() checks priority order |
| `check_permission(action, product_permissions, domain) -> PermissionCheck` | `autoservice/permission.py:279` | Top-level convenience function to check permission using product-specific or default domain permissions |
| `get_default_permissions(domain) -> OperatorPermissions` | `autoservice/permission.py:269` | Get default OperatorPermissions for a domain ('customer-service' or 'marketing') |
| `MockDB(db_path)` | `autoservice/mock_db.py:149` | SQLite mock database manager with 9 tables and full CRUD for all entity types |
| `MockDB.upsert_customer(...)` | `autoservice/mock_db.py:166` | Insert or replace a customer record |
| `MockDB.get_customer(identifier)` | `autoservice/mock_db.py:188` | Get customer by ID or phone number |
| `MockDB.upsert_product(...)` | `autoservice/mock_db.py:216` | Insert or replace a product record with JSON data blob |
| `MockDB.get_product(product_id)` | `autoservice/mock_db.py:233` | Get product by ID |
| `MockDB.get_product_full_data(product_id)` | `autoservice/mock_db.py:240` | Get full product data from data_json column |
| `MockDB.add_subscription(...)` | `autoservice/mock_db.py:250` | Insert or replace a subscription |
| `MockDB.get_subscriptions(customer_id, service_name)` | `autoservice/mock_db.py:268` | Get subscriptions for a customer, optionally filtered |
| `MockDB.add_billing_transaction(...)` | `autoservice/mock_db.py:284` | Insert or replace a billing transaction |
| `MockDB.get_billing(customer_id, start_date, end_date)` | `autoservice/mock_db.py:301` | Get billing transactions with optional date range and computed totals |
| `MockDB.add_order(...)` | `autoservice/mock_db.py:324` | Insert or replace an order |
| `MockDB.get_purchases(customer_id)` | `autoservice/mock_db.py:343` | Get purchase history with total_spent and last_purchase_date |
| `MockDB.get_order(order_id)` | `autoservice/mock_db.py:358` | Get order by ID with computed items and delivery_info |
| `MockDB.set_product_pricing(...)` | `autoservice/mock_db.py:377` | Insert or replace product pricing with special offers and trial options |
| `MockDB.get_product_pricing(product_id)` | `autoservice/mock_db.py:391` | Get product pricing with deserialized JSON fields |
| `MockDB.add_product_feature(...)` | `autoservice/mock_db.py:406` | Insert a product feature record |
| `MockDB.get_product_feature(product_id, feature_name)` | `autoservice/mock_db.py:420` | Get product feature by product_id and feature_name (LIKE match) |
| `MockDB.add_service(...)` | `autoservice/mock_db.py:432` | Insert or replace a service listing |
| `MockDB.get_services(category)` | `autoservice/mock_db.py:447` | Get services optionally filtered by category |
| `MockDB.set_permission_rules(product_id, domain, rules)` | `autoservice/mock_db.py:461` | Set permission rules for a product+domain |
| `MockDB.get_permission_rules(product_id, domain)` | `autoservice/mock_db.py:476` | Get permission rules as dict of level->[rules] |
| `MockDB.log_api_call(endpoint, method, params, response)` | `autoservice/mock_db.py:497` | Log an API call to the audit log table |
| `PluginTool` (dataclass) | `autoservice/plugin_loader.py:27` | An MCP tool declared by a plugin: name, description, handler, input_schema, plugin_name |
| `PluginRoute` (dataclass) | `autoservice/plugin_loader.py:36` | An HTTP route declared by a plugin: path, method, handler, plugin_name |
| `Plugin` (dataclass) | `autoservice/plugin_loader.py:46` | Fully loaded plugin with tools, routes, references, optional MockDB |
| `load_plugin(plugin_dir: Path) -> Plugin` | `autoservice/plugin_loader.py:142` | Load a single plugin from its directory: parse plugin.yaml, resolve handlers, init mock DB |
| `discover(plugins_dir) -> list[Plugin]` | `autoservice/plugin_loader.py:229` | Discover and load all plugins from a directory; skips hidden dirs |
| `upsert_contact(open_id, name, phone, email, company, department, job_title) -> dict` | `autoservice/crm.py:67` | Create or update a Feishu contact by open_id |
| `increment_message_count(open_id) -> None` | `autoservice/crm.py:122` | Bump message_count and last_seen for a contact |
| `log_message(open_id, chat_id, direction, text, ts) -> None` | `autoservice/crm.py:133` | Log a conversation message (direction: 'in' or 'out') |
| `get_contact(open_id) -> dict | None` | `autoservice/crm.py:145` | Get a contact by open_id |
| `get_contact_history(open_id, limit) -> list[dict]` | `autoservice/crm.py:152` | Get recent conversation history for a contact |
| `list_contacts(limit) -> list[dict]` | `autoservice/crm.py:162` | List all contacts, most recently active first |
| `search_contacts(query) -> list[dict]` | `autoservice/crm.py:171` | Search contacts by name, company, phone, or email using LIKE |
| `add_rule(scope, rule, scope_value, context, created_by) -> dict` | `autoservice/crm.py:189` | Insert a new customer rule into customer_rules table |
| `list_rules(scope, context) -> list[dict]` | `autoservice/crm.py:211` | List rules with optional scope/context filters |
| `get_rules_for_customer(open_id, region) -> list[dict]` | `autoservice/crm.py:229` | Get all rules applicable to a customer (global, customer-specific, or region-based) |
| `delete_rule(rule_id) -> bool` | `autoservice/crm.py:249` | Delete a customer rule by id |
| `update_rule(rule_id, **kwargs) -> dict | None` | `autoservice/crm.py:257` | Update allowed fields on a customer rule |
| `ConversationLogger(base_path)` | `autoservice/logger.py:16` | Logs conversation history to JSON files in .autoservice/database/history/ |
| `ConversationLogger.log_user_input(text)` | `autoservice/logger.py:44` | Record a user input message with timestamp |
| `ConversationLogger.log_message(msg)` | `autoservice/logger.py:53` | Record an assistant/agent message with serialization |
| `CustomerManager(domain, config)` | `autoservice/customer_manager.py:24` | Manages customer records on disk (JSON files) with cold-start support |
| `CustomerManager.lookup_by_phone(phone) -> tuple` | `autoservice/customer_manager.py:37` | Search customers by phone number |
| `CustomerManager.lookup_by_id(id) -> tuple` | `autoservice/customer_manager.py:65` | Search customers by ID (directory prefix or _id field) |
| `CustomerManager.lookup_by_name(name) -> tuple` | `autoservice/customer_manager.py:99` | Search customers by name (partial/bidirectional contains match) |
| `CustomerManager.create_cold_start_customer(phone) -> tuple` | `autoservice/customer_manager.py:128` | Create a minimal customer record for unknown callers |
| `CustomerManager.update_customer(dir_path, updates, session) -> dict` | `autoservice/customer_manager.py:172` | Update customer info after a call; appends session to interaction_history |
| `CustomerManager.get_or_create(identifier) -> tuple` | `autoservice/customer_manager.py:225` | Lookup by ID/phone/name or create cold-start; returns (data, path, is_new) |
| `load_rules() -> list[dict]` | `autoservice/rules.py:10` | Load all rules from all YAML files in .autoservice/rules/ |
| `save_rules(filename, rules) -> Path` | `autoservice/rules.py:27` | Save a list of rule dicts to a named YAML file |
| `add_rule(context, rule, created_by, filename) -> dict` | `autoservice/rules.py:35` | Add a rule with auto-incrementing ID to a YAML file |
| `delete_rule(rule_id, filename) -> bool` | `autoservice/rules.py:55` | Delete a rule by ID from a specified YAML file |
| `format_rules_for_prompt() -> str` | `autoservice/rules.py:69` | Format all universal rules as text block for channel system instructions |

**依赖关系**：
- -> `httpx` (HTTP client for APIClient)
- -> `PyYAML` (config loading, plugin_loader, rules)
- -> `claude_agent_sdk` (Claude Agent SDK integration in claude.py)
- -> `python-docx` / `openpyxl` / `pdfplumber` (auto-installed by importer.py for file extraction)
- -> `sqlite3` (stdlib; CRM database, MockDB)
- Internal: `customer_manager` -> `core`, `config`; `database` -> `core`, `config`; `importer` -> `core`, `config`; `session` -> `core`, `config`; `plugin_loader` -> `mock_db`

**对应用户流程**：
- Plugin discovery and loading: `discover()` scans plugins/ for `plugin.yaml`, resolves handlers, inits MockDB with seed data (`autoservice/plugin_loader.py:229`)
- Record CRUD (file-based database): save/list/get/update/delete records as info.json + README.md in named subdirectories (`autoservice/database.py:30`)
- Customer cold-start flow: lookup by ID/phone/name, create minimal record if unknown, enrich after call (`autoservice/customer_manager.py:225`)
- Session lifecycle: detect Claude session ID, generate formatted session ID, create directory, save conversation (`autoservice/session.py:122`)
- Permission check flow: check action against 4-level priority rules (forbidden > requires_process > requires_supervisor > can_approve) (`autoservice/permission.py:279`)
- CRM contact tracking: upsert_contact on first message, increment counts, log messages, retrieve applicable rules (`autoservice/crm.py:67`)
- Mock API serving: MockDB with 9-table schema, seeded from JSON, provides CRUD for all entity types (`autoservice/mock_db.py:146`)
- Data import from files: extract from DOCX/XLSX/PDF, persist each item as info.json + README.md (`autoservice/importer.py:149`)
- Claude Agent SDK integration: execute query with proxy-aware env and plugin path, yield raw message objects (`autoservice/claude.py:13`)

---

### feishu

**职责**：Feishu IM channel -- MCP stdio bridge (`channel.py`) and standalone WebSocket message-routing daemon (`channel_server.py`) for multi-instance customer service (`feishu/channel.py:1`)

**关键接口**：

| 接口 | 位置 | 说明 |
|------|------|------|
| `ChannelClient(server_url, chat_ids, instance_id, runtime_mode)` | `feishu/channel.py:60` | WebSocket client connecting to channel_server with auto-reconnect, message queue, and reply/react/UX event methods |
| `ChannelClient.connect()` | `feishu/channel.py:69` | Connects to channel-server WebSocket with infinite auto-reconnect loop (3s retry) |
| `ChannelClient.send_reply(chat_id, text)` | `feishu/channel.py:106` | Sends a reply message to channel-server via WebSocket |
| `ChannelClient.send_react(message_id, emoji_type)` | `feishu/channel.py:112` | Sends an emoji reaction to channel-server via WebSocket |
| `ChannelClient.send_ux_event(chat_id, event, data)` | `feishu/channel.py:118` | Sends a UX event to channel-server via WebSocket |
| `inject_message(write_stream, msg)` | `feishu/channel.py:135` | Builds JSONRPCNotification with channel metadata and sends into MCP write_stream as SessionMessage |
| `create_server() -> Server` | `feishu/channel.py:227` | Creates MCP Server('autoservice-channel') with built instructions from identity.yaml + channel-instructions.md |
| `register_tools(server, plugin_tools)` | `feishu/channel.py:237` | Registers core tools (reply, react) and dynamic plugin tools on the MCP server via list_tools/call_tool handlers |
| `entry_point()` | `feishu/channel.py:371` | Synchronous wrapper calling asyncio.run(main()), used as console_scripts entry point |
| `ChannelServer(host, port, feishu_enabled, admin_chat_id)` | `feishu/channel_server.py:55` | Local WebSocket server (default port 9999) routing messages between Feishu, web clients, and Claude Code instances |
| `ChannelServer.start()` | `feishu/channel_server.py:84` | Starts WebSocket server via websockets.serve and optionally launches Feishu WS integration task |
| `ChannelServer.stop()` | `feishu/channel_server.py:103` | Gracefully shuts down: cancels background tasks, closes WebSocket server, notifies admin |
| `ChannelServer.route_message(chat_id, message)` | `feishu/channel_server.py:860` | Three-tier routing: exact match -> prefix match -> wildcard broadcast; adds routed_to hint |
| `ChannelServer.status_text() -> str` | `feishu/channel_server.py:986` | Generates human-readable status report: message stats, service desks, channel status, active conversations |
| `ChannelServer.help_text() -> str` | `feishu/channel_server.py:1036` | Generates help text listing all admin slash-commands (/status, /help, /inject, /explain) |
| `ChannelServer._load_credentials()` | `feishu/channel_server.py:147` | Loads Feishu app_id/app_secret from env vars or .feishu-credentials.json |
| `ChannelServer._resolve_user(open_id)` | `feishu/channel_server.py:176` | Resolves Feishu open_id to display name via cache, Feishu contact API, and CRM upsert_contact |
| `ChannelServer._download_feishu_file(...)` | `feishu/channel_server.py:274` | Downloads file/image/audio/media attachments from Feishu API, saves to .autoservice/uploads/{chat_id}/ |
| `ChannelServer._handle_admin_message(...)` | `feishu/channel_server.py:341` | Processes admin slash-commands: /help, /status, /inject #N text, /explain query |
| `ChannelServer._reply_feishu(chat_id, text)` | `feishu/channel_server.py:408` | Sends text message to a Feishu chat via CreateMessageRequest in a daemon thread |
| `ChannelServer._handle_client(ws)` | `feishu/channel_server.py:754` | Handles a single WebSocket client connection: dispatches register/reply/react/message/ux_event/pong |
| `ChannelServer._handle_register(ws, data)` | `feishu/channel_server.py:789` | Registers an instance into exact_routes/prefix_routes/wildcard_instances |
| `ChannelServer._unregister(ws)` | `feishu/channel_server.py:835` | Removes a disconnected instance from all route tables |
| `ChannelServer._handle_reply(data)` | `feishu/channel_server.py:905` | Reverse-routes replies: oc_* -> Feishu API, web_* -> web relay |
| `ChannelServer._handle_ux_event(data)` | `feishu/channel_server.py:955` | Forwards UX events to the appropriate web connection via exact/prefix route lookup |
| `Instance` (dataclass) | `feishu/channel_server.py:37` | Registered channel.py or web/app.py WebSocket client with ws, instance_id, role, chat_ids, runtime_mode |
| `main()` | `feishu/channel_server.py:1138` | Synchronous entry point calling asyncio.run(_async_main()) |
| `_async_main()` | `feishu/channel_server.py:1090` | Async entry point: configures logging, reads env vars, creates ChannelServer, registers signal handlers |

**依赖关系**：
- -> `websockets` (WebSocket server and client)
- -> `mcp.server` (MCP stdio server, types, session messages)
- -> `anyio` (parallel task group in channel.py main)
- -> `lark_oapi` (lazy; Feishu API SDK for WS client, message creation, contact lookup)
- -> `requests` (lazy; HTTP token fetch for startup notifications)
- -> `autoservice.plugin_loader` (lazy; discover() in main)
- -> `autoservice.crm` (lazy; upsert_contact, increment_message_count, log_message)
- -> `yaml` (lazy; _load_identity for identity.yaml)

**对应用户流程**：
- Feishu message ingestion and routing: channel_server receives P2ImMessageReceiveV1, parses, deduplicates, routes via 3-tier routing (`feishu/channel_server.py:443`)
- MCP channel bridge: channel.py discovers plugins, creates ChannelClient + MCP Server, runs 3 parallel tasks (server.run, client.connect, consume_messages) (`feishu/channel.py:318`)
- Reply flow (Claude Code -> Feishu user): Claude calls 'reply' MCP tool -> ChannelClient sends to channel_server -> Feishu API or web relay (`feishu/channel.py:293`)
- Admin command flow: admin sends /status, /help, /inject, /explain in admin chat -> processed by _handle_admin_message (`feishu/channel_server.py:341`)
- Web client message flow: web/app.py connects to channel_server, registers with web_* prefix, messages routed/relayed (`feishu/channel_server.py:941`)
- Instance registration and routing: register with exact/prefix/wildcard patterns, 3-tier priority routing, cleanup on disconnect (`feishu/channel_server.py:789`)

---

### web

**职责**：FastAPI web chat channel with access-code authentication, WebSocket relay to channel-server, session persistence, plugin KB integration, and branded chat UI (`web/app.py:123`)

**关键接口**：

| 接口 | 位置 | 说明 |
|------|------|------|
| `GET /` | `web/app.py:137` | Redirects to /login |
| `GET /login` | `web/app.py:142` | Serves login.html |
| `GET /chat` | `web/app.py:147` | Serves chat.html (plugin or built-in) |
| `GET /explain/{path}` | `web/app.py:165` | Serves explain flow visualization HTML pages from .autoservice/explain/ |
| `GET /api/kb_search?query=&top_k=&source_filter=&countries=` | `web/app.py:181` | Knowledge base search endpoint |
| `GET /api/route_query?query=` | `web/app.py:205` | Route customer query to domain/region/role |
| `POST /api/save_lead` | `web/app.py:215` | Save collected lead data (new_customer/existing_customer/partner) |
| `GET /api/sessions?token=` | `web/app.py:252` | List up to 50 sessions for authenticated user |
| `GET /api/sessions/{session_id}?token=` | `web/app.py:279` | Get session detail by ID |
| `GET /api/changelog?lang=` | `web/app.py:300` | Get changelog version and content with EN/ZH i18n |
| `GET /static/*` (mount) | `web/app.py:124` | Static file serving from web/static/ |
| `GET /admin/new-code?key=&expires_in=&label=` | `web/auth.py:162` | Generate 1 access code (admin key required) |
| `GET /admin/batch-codes?key=&count=&expires_in=&label=` | `web/auth.py:190` | Batch generate 1-50 access codes (admin key required) |
| `GET /admin/codes?key=` | `web/auth.py:228` | List all access codes with status (admin key required) |
| `POST /auth/verify` | `web/auth.py:245` | Verify access code, return session token; enforces exclusive lock |
| `POST /auth/logout` | `web/auth.py:280` | Release session token and code lock |
| `WS /ws` | `web/websocket.py:132` | Generic WebSocket (sends error, directs to /ws/chat) |
| `WS /ws/chat` | `web/websocket.py:143` | Authenticated chat WebSocket with channel-server relay |
| `WS /ws/cinnox` | `web/app.py:176` | Alias for /ws/chat used by cinnox.html plugin chat page |
| `lifespan(app)` | `web/app.py:85` | FastAPI lifespan: starts idle_purge_loop, discovers plugins, mounts plugin HTTP routes |
| `configure()` (auth) | `web/auth.py:27` | Sets admin_key, idle_timeout_seconds, and auth_file path |
| `_Code` (dataclass) | `web/auth.py:40` | Access code with code, expires_at, label, status, created_at; has is_usable property |
| `valid_token(token) -> bool` | `web/auth.py:156` | Validates a session token (calls purge first to evict stale tokens) |
| `idle_purge_loop()` | `web/auth.py:149` | Background async task sweeping idle/expired tokens every 60 seconds |
| `save_auth()` | `web/auth.py:71` | Persists all auth state (codes, tokens, mappings) to auth_store.json |
| `load_auth()` | `web/auth.py:96` | Loads auth state from auth_store.json on startup |
| `configure()` (plugin_kb) | `web/plugin_kb.py:22` | Sets search paths for KB and route query scripts |
| `get_kb_search()` | `web/plugin_kb.py:37` | Lazy-loads and returns the KB search module |
| `get_route_query()` | `web/plugin_kb.py:51` | Lazy-loads and returns the route query module |
| `presearch_kb(prompt) -> (augmented_prompt, hit_count)` | `web/plugin_kb.py:65` | Pre-searches KB before calling Claude, injects results as context |
| `configure()` (session_persistence) | `web/session_persistence.py:18` | Sets the sessions directory path |
| `new_web_session_id() -> str` | `web/session_persistence.py:24` | Generates a new session ID with timestamp format session_YYYYMMDD_HHMMSS |
| `session_dir_for_code(code) -> Path` | `web/session_persistence.py:28` | Returns per-code subdirectory under SESSIONS_DIR |
| `infer_session_meta(messages) -> dict` | `web/session_persistence.py:36` | Infers customer_type and resolution from conversation text using keyword matching |
| `save_session_data(session_id, data, code)` | `web/session_persistence.py:95` | Saves session JSON to per-code subdirectory |
| `load_session_data(session_id, code_hint) -> dict` | `web/session_persistence.py:102` | Loads session data by ID with fast path (code_hint) and fallback (scan all subdirectories) |
| `configure()` (websocket) | `web/websocket.py:29` | Sets channel-server WebSocket URL |
| `WebChannelBridge` (class) | `web/websocket.py:35` | Singleton maintaining single WS connection to channel-server, multiplexing all browser sessions |
| `WebChannelBridge.ensure_connected()` | `web/websocket.py:45` | Connects to channel-server, sends register, waits for ack, starts receive loop |
| `WebChannelBridge._receive_loop()` | `web/websocket.py:72` | Async receive loop: demultiplexes messages by chat_id to subscriber queues |
| `WebChannelBridge.subscribe(chat_id) -> Queue` | `web/websocket.py:105` | Creates and returns an asyncio.Queue for a chat_id |
| `WebChannelBridge.unsubscribe(chat_id)` | `web/websocket.py:110` | Removes subscriber queue for a chat_id |
| `WebChannelBridge.send_message(msg)` | `web/websocket.py:113` | Sends a JSON message over the bridge connection |

**依赖关系**：
- -> `fastapi` (FastAPI app, HTTPException, WebSocket, StaticFiles)
- -> `websockets` (lazy; WebSocket client in WebChannelBridge)
- -> `uvicorn` (conditional; ASGI server in __main__ block)
- -> `autoservice.plugin_loader` (lazy; discover() in lifespan)
- -> `web.auth` (authentication module)
- -> `web.plugin_kb` (knowledge base search integration)
- -> `web.session_persistence` (session data persistence)
- -> `web.websocket` (WebSocket handlers and channel bridge)
- -> `marked.js` (frontend; markdown rendering in cinnox.html)

**对应用户流程**：
- Access Code Login: user enters code on /login, POST /auth/verify validates and returns session token, redirect to /chat (`web/app.py:137`)
- Authenticated Chat Session: /chat serves cinnox.html, opens WS to /ws/chat, 3 concurrent tasks (browser_to_server, server_to_browser, heartbeat) (`web/websocket.py:143`)
- Session Resume: user clicks session in history, fetches detail, sends resume_session over WS, server replays conversation (`web/static/cinnox.html:1926`)
- End Session and Logout: end_session saves and marks resolved, logout releases code lock and redirects to /login (`web/static/cinnox.html:1646`)
- KB Search (HTTP API): GET /api/kb_search lazy-loads KB module, returns filtered results (`web/app.py:181`)
- Admin Code Management: /admin/new-code, /admin/batch-codes, /admin/codes endpoints with admin key (`web/auth.py:162`)
- Mode Switching (Sales/Service): UI tab switch closes WS, resets chat, reconnects with new mode (`web/static/cinnox.html:1163`)

---

### plugins

**职责**：Customer-specific declarative plugins providing MCP tools and HTTP routes, loaded at runtime by plugin_loader via importlib (`plugins/_example/plugin.yaml:1`)

**关键接口**：

| 接口 | 位置 | 说明 |
|------|------|------|
| `echo(message: str) -> dict` | `plugins/_example/tools.py:15` | MCP tool handler; returns {'echo': message} |
| `lookup(id: str) -> dict` | `plugins/_example/tools.py:20` | MCP tool handler; looks up a record by ID from in-memory _RECORDS |
| `post_echo(message: str) -> dict` | `plugins/_example/routes.py:20` | HTTP POST /api/example/echo handler; delegates to tools.echo |
| `get_record(record_id: str) -> dict` | `plugins/_example/routes.py:26` | HTTP GET /api/example/{record_id} handler; delegates to tools.lookup |
| `set_db(db: MockDB) -> None` | `plugins/cinnox/tools.py:27` | Sets the global MockDB instance for all CINNOX tools |
| `customer_lookup(identifier: str) -> dict` | `plugins/cinnox/tools.py:48` | MCP tool: looks up CINNOX customer by identifier via db.get_customer() |
| `billing_query(account_id, start_date, end_date) -> dict` | `plugins/cinnox/tools.py:58` | MCP tool: gets billing history via db.get_billing() with optional date range |
| `subscription_query(account_id: str) -> dict` | `plugins/cinnox/tools.py:70` | MCP tool: gets active subscriptions via db.get_subscriptions() |
| `permission_check(action, product_id) -> dict` | `plugins/cinnox/tools.py:83` | MCP tool: checks operator permissions via autoservice.permission.check_permission |
| `get_customer(identifier: str) -> dict` | `plugins/cinnox/routes.py:18` | HTTP GET /api/cinnox/customers/{identifier} handler |
| `get_billing(account_id, start_date, end_date) -> dict` | `plugins/cinnox/routes.py:24` | HTTP GET /api/cinnox/customers/{account_id}/billing handler |
| `get_subscriptions(account_id: str) -> dict` | `plugins/cinnox/routes.py:30` | HTTP GET /api/cinnox/customers/{account_id}/subscriptions handler |
| `_get_tools()` (_example) | `plugins/_example/routes.py:15` | Lazy-imports tools module from sys.modules['autoservice.plugins._example.tools'] |
| `_get_tools()` (cinnox) | `plugins/cinnox/routes.py:13` | Lazy-imports tools module from sys.modules['autoservice.plugins.cinnox.tools'] |
| `_envelope(data, error) -> dict` | `plugins/cinnox/tools.py:33` | Wraps response in standard API envelope with success/data/error/timestamp/mode |
| `_RECORDS` (dict) | `plugins/_example/tools.py:9` | In-memory dict of 2 example records (EX-001, EX-002) |
| `accounts.json` (seed data) | `plugins/cinnox/mock_data/accounts.json:1` | 6 CINNOX customer account records (ACC-1001 through ACC-6006) |
| `glossary.json` (reference) | `plugins/cinnox/references/glossary.json:1` | ~350 CINNOX/telecom domain terms with descriptions and related terms |
| `synonym-map.json` (reference) | `plugins/cinnox/references/synonym-map.json:1` | 35 abbreviations/synonyms mapped to canonical telecom terms |

**依赖关系**：
- -> `autoservice.mock_db.MockDB` (plugins/cinnox/tools.py:11)
- -> `autoservice.permission.check_permission` (plugins/cinnox/tools.py:12)
- -> `sys.modules['autoservice.plugins._example.tools']` (plugins/_example/routes.py:17)
- -> `sys.modules['autoservice.plugins.cinnox.tools']` (plugins/cinnox/routes.py:15)

**对应用户流程**：
- MCP tool dispatch (example plugin): plugin_loader reads plugin.yaml, imports tools.py, registers MCP tools; on call, handler invokes tools.echo() or tools.lookup() (`plugins/_example/plugin.yaml:7`)
- HTTP route dispatch (example plugin): plugin_loader mounts HTTP routes, route handlers call _get_tools() then delegate to tool functions (`plugins/_example/plugin.yaml:30`)
- CINNOX customer lookup (MCP + HTTP): plugin loads tools.py, injects MockDB seeded from accounts.json, tools.customer_lookup() queries db (`plugins/cinnox/tools.py:48`)
- CINNOX billing query: MCP tool or HTTP endpoint invokes tools.billing_query() with optional date range (`plugins/cinnox/tools.py:58`)
- CINNOX permission check: MCP tool checks product-specific permissions via autoservice.permission.check_permission() (`plugins/cinnox/tools.py:83`)

---

### tests

**职责**：Unit and E2E tests covering channel-server routing, channel-client registration, web relay bridge, explain command pipeline, and full integration flows (`tests/test_channel_server.py:1`)

**关键接口**：

| 接口 | 位置 | 说明 |
|------|------|------|
| `test_channel_connects_and_registers` | `tests/test_channel_client.py:10` | Tests ChannelClient connects to mock WS server and sends register with correct type, chat_ids, instance_id |
| `test_server_accepts_connection` | `tests/test_channel_server.py:52` | Tests channel-server accepts WebSocket connections and keeps them open |
| `test_register_and_route` | `tests/test_channel_server.py:64` | Tests registering a client with a specific chat_id then routing a message to it |
| `test_wildcard_receives_copy` | `tests/test_channel_server.py:98` | Tests wildcard (*) registered instance receives a copy of routed messages with routed_to hint |
| `test_registration_conflict` | `tests/test_channel_server.py:152` | Tests registering the same chat_id twice produces REGISTRATION_CONFLICT error |
| `test_unregister_on_disconnect` | `tests/test_channel_server.py:187` | Tests disconnecting clears routes from exact_routes and _ws_to_instance map |
| `test_inbound_message_routing` | `tests/test_channel_server.py:214` | Tests messages from unregistered web clients get routed to wildcard-registered instances |
| `TestExplainCommand.test_explain_no_query_returns_usage` | `tests/test_explain_command.py:29` | Tests /explain with no query returns a Usage message |
| `TestExplainCommand.test_explain_routes_to_wildcard` | `tests/test_explain_command.py:38` | Tests /explain with query routes explain-mode message to admin_explain chat_id |
| `TestExplainCommand.test_help_includes_explain` | `tests/test_explain_command.py:56` | Tests help_text() output includes /explain |
| `TestFlowYAML.test_index_has_all_flows` | `tests/test_explain_command.py:63` | Tests _index.yaml lists all flow YAML files in .autoservice/flows/ |
| `TestFlowYAML.test_flow_has_required_fields` | `tests/test_explain_command.py:75` | Tests each flow YAML has required fields: id, name, description, tags, entry, exits, nodes, edges |
| `TestFlowYAML.test_flow_entry_node_exists` | `tests/test_explain_command.py:89` | Tests each flow's entry references an existing node id |
| `TestFlowYAML.test_flow_edges_reference_valid_nodes` | `tests/test_explain_command.py:102` | Tests all edges reference valid node ids |
| `TestExplainRoute.test_explain_serves_existing_file` | `tests/test_explain_command.py:120` | Tests GET /explain/file.html serves existing file from .autoservice/explain/ |
| `TestExplainRoute.test_explain_404_for_missing` | `tests/test_explain_command.py:136` | Tests GET /explain/nonexistent.html returns 404 |
| `test_web_bridge_connects_and_registers` | `tests/test_web_relay.py:10` | Tests WebChannelBridge connects and registers with chat_ids=['web_*'] and role='web' |
| `test_web_bridge_demuxes_replies` | `tests/test_web_relay.py:52` | Tests WebChannelBridge demultiplexes replies to correct subscriber queue by chat_id |
| `main()` (e2e feishu mock) | `tests/e2e/test_feishu_mock.py:37` | 7 E2E tests: wildcard registration, message routing, mode fields, reply protocol, dual routing, conflict, status text |
| `test_web_chat.sh` | `tests/e2e/test_web_chat.sh:1` | Full browser E2E: start services, generate code, login, chat, send message, end session, logout |
| `_start_server(port)` | `tests/test_channel_server.py:21` | Helper: creates and starts ChannelServer with feishu_enabled=False |
| `_stop_server(server)` | `tests/test_channel_server.py:30` | Helper: stops a running ChannelServer |
| `_connect(port)` | `tests/test_channel_server.py:34` | Helper: opens websockets client connection to the server |
| `_send_json(ws, data)` | `tests/test_channel_server.py:38` | Helper: sends a dict as JSON over WebSocket |
| `_recv_json(ws, timeout)` | `tests/test_channel_server.py:42` | Helper: receives and parses a JSON message with timeout |
| `server` (fixture) | `tests/test_explain_command.py:17` | pytest fixture: creates ChannelServer with feishu_enabled=False and admin_chat_id='oc_admin_test' |

**依赖关系**：
- -> `feishu.channel` (ChannelClient -- test_channel_client.py)
- -> `feishu.channel_server` (ChannelServer -- test_channel_server.py, test_explain_command.py, e2e/test_feishu_mock.py)
- -> `web.websocket` (WebChannelBridge -- test_web_relay.py)
- -> `web.app` (FastAPI app -- test_explain_command.py, e2e/test_web_chat.sh)
- -> `.autoservice/flows/` (YAML flow definitions -- test_explain_command.py)
- -> `pytest` / `pytest-asyncio` (test framework)
- -> `websockets` (mock WebSocket servers in tests)
- -> `fastapi.testclient` (HTTP test client for web app routes)
- -> `pyyaml` (YAML parsing for flow definition tests)
- -> `agent-browser` (browser automation for e2e/test_web_chat.sh only)

**对应用户流程**：

Test coverage map:

- `tests/test_channel_client.py` -> `feishu.channel` (ChannelClient connect and register protocol)
- `tests/test_channel_server.py` -> `feishu.channel_server` (WebSocket routing: accept, register, route, wildcard, conflict, disconnect cleanup, inbound routing)
- `tests/test_explain_command.py` -> `feishu.channel_server` (admin /explain command) + `.autoservice/flows/` (YAML schema validation) + `web.app` (/explain/* HTTP route)
- `tests/test_web_relay.py` -> `web.websocket` (WebChannelBridge connect, register, reply demultiplexing)
- `tests/e2e/test_feishu_mock.py` -> `feishu.channel_server` (full E2E: registration, routing, mode preservation, reply, dual routing, conflict, status text)
- `tests/e2e/test_web_chat.sh` -> `web.app` + `feishu.channel_server` (full browser E2E: login, chat, send message, end session, logout)

Summary: 5 Python test files + 1 shell test file, 13 pytest test functions, 7 E2E test scenarios.

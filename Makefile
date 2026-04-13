.PHONY: setup run-channel run-web run-server check e2e-web e2e-feishu pool-status pool-start pool-test sync sync-dry sync-status sync-all refine

# --- Setup ---
# Create symlinks from .claude/ to top-level dirs, discover plugin skills,
# and create .autoservice/ runtime directories.
setup:
	@echo "==> Linking top-level dirs into .claude/"
	@mkdir -p .claude
	@for dir in skills commands agents hooks; do \
		rm -f .claude/$$dir; \
		ln -sfn ../$$dir .claude/$$dir; \
		echo "  .claude/$$dir -> ../$$dir"; \
	done
	@echo "==> Scanning plugins for skills..."
	@for skill_dir in plugins/*/skills/*/; do \
		[ -d "$$skill_dir" ] || continue; \
		name=$$(basename "$$skill_dir"); \
		rm -f skills/$$name; \
		ln -sfn ../$$skill_dir skills/$$name; \
		echo "  skills/$$name -> ../$$skill_dir"; \
	done
	@echo "==> Creating .autoservice/ runtime dirs"
	@mkdir -p .autoservice/logs .autoservice/data .autoservice/cache
	@echo "Done."

# --- Run ---
run-channel:
	uv run python3 channels/feishu/channel.py

run-web:
	@mkdir -p .autoservice/logs
	uv run uvicorn channels.web.app:app --host 0.0.0.0 --port $${DEMO_PORT:-8000} --log-level info 2>&1 | tee -a .autoservice/logs/web.log

run-server:
	uv run python3 channels/feishu/channel_server.py

# --- E2E Tests ---
e2e-web:
	bash tests/e2e/test_web_chat.sh

e2e-feishu:
	uv run python3 tests/e2e/test_feishu_mock.py

# --- CC Pool ---
pool-status:
	uv run python -m autoservice.cc_pool_cli status

pool-start:
	uv run python -m autoservice.cc_pool_cli start

pool-logs:
	uv run python -m autoservice.cc_pool_cli logs

pool-test:
	uv run python tests/integration_cc_pool.py

pool-unit:
	uv run python -m pytest tests/test_cc_pool.py -v

# --- Check ---
# Verify plugin discovery by listing discovered skill symlinks.
check:
	@echo "==> Checking plugin discovery"
	@found=0; \
	for link in skills/*/; do \
		[ -L "$${link%/}" ] && { echo "  plugin skill: $${link%/}"; found=$$((found+1)); }; \
	done; \
	echo "Found $$found plugin skill(s)."

# --- Sync & Refine ---
sync:
	@bash scripts/sync.sh

sync-dry:
	@bash scripts/sync.sh --dry-run

sync-status:
	@bash scripts/sync-status.sh

sync-all:
	@bash scripts/sync-all.sh

refine:
	@bash scripts/refine.sh

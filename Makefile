.PHONY: help install test run refresh queue channel-info post-now clean

help:
	@echo "ParisExplorer YouTube Automation - Available Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install        - Install Python dependencies"
	@echo "  make test           - Run system tests"
	@echo ""
	@echo "Operations:"
	@echo "  make run            - Start scheduler (continuous mode)"
	@echo "  make post-now       - Post immediately"
	@echo "  make refresh        - Refresh content sources"
	@echo "  make queue          - Show content queue"
	@echo "  make channel-info   - Show YouTube channel info"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Clean temporary files"
	@echo "  make logs           - View logs"

install:
	pip install -r requirements.txt
	@echo ""
	@echo "✓ Dependencies installed"
	@echo "Next: Setup YouTube API credentials (see SETUP.md)"

test:
	python test_system.py

run:
	python automation.py --mode scheduler

post-now:
	python automation.py --mode post-now

refresh:
	python automation.py --mode refresh

queue:
	python automation.py --mode queue

channel-info:
	python automation.py --mode channel-info

clean:
	rm -rf __pycache__/
	rm -rf temp/*
	rm -f *.pyc
	find . -type d -name __pycache__ -exec rm -rf {} +
	@echo "✓ Cleaned temporary files"

logs:
	@if [ -f logs/automation.log ]; then \
		tail -50 logs/automation.log; \
	else \
		echo "No logs found. Run automation first."; \
	fi

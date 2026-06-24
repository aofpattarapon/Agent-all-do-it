-- Phase 3 DB schema check + Phase 4 re-check

select version();

select version_num from alembic_version;

select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name = 'crypto_raw_payloads';

select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'trade_proposals'
  and column_name = 'raw_payload';

select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'trade_journal'
  and column_name = 'raw_facts';

select column_name
from information_schema.columns
where table_schema = 'public'
  and table_name = 'runs'
order by ordinal_position;

select column_name
from information_schema.columns
where table_schema = 'public'
  and table_name = 'run_steps'
order by ordinal_position;

select
  (select count(*) from trade_proposals where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586') as trade_proposals,
  (select count(*) from trade_executions where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586') as trade_executions,
  (select count(*) from trade_journal where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586') as trade_journal,
  (select count(*) from market_snapshots where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586') as market_snapshots;

select id, status, pause_reason, current_step_index, workflow_id, created_at
from runs
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by created_at desc
limit 10;

select run_id, step_key, status, created_at
from run_steps
order by created_at desc
limit 15;

select run_id, event_type, created_at
from trace_events
order by created_at desc
limit 20;

select run_id, step_key, status, left(coalesce(output_json::text, ''), 240) as output_preview
from run_steps
where run_id = 'e09ccbf4-5349-4307-b1f5-f1eb7f1f4781'
order by created_at;

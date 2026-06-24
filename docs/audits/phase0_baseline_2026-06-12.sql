-- Phase 0 baseline SQL capture
-- Project scope: 288bc95a-b4da-46e7-bdfa-b5630233f586

select id, name, slug, status, created_at
from projects
order by created_at desc
limit 10;

select key, value
from app_settings
where key like 'project.288bc95a-b4da-46e7-bdfa-b5630233f586.%'
   or key like 'trading.%'
   or key like '%runtime_profile%'
order by key;

select name, role, is_active, order_index, runtime_kind, model, max_tokens, temperature, memory_type, context_window_size,
       tools_config->'fallback_chain' as fallback_chain,
       tools_config->>'gate_policy' as gate_policy
from agent_configs
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by order_index;

select name, trigger_kind, is_enabled, definition_json
from workflows
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by created_at;

select w.name as workflow_name,
       s.ord as step_order,
       s.step_json->>'key' as step_key,
       s.step_json->>'kind' as step_kind,
       s.step_json->>'label' as label,
       s.step_json->>'agent_key' as agent_key
from workflows w
cross join lateral jsonb_array_elements(w.definition_json->'steps') with ordinality as s(step_json, ord)
where w.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by w.name, s.ord;

select w.name as workflow_name, s.id, s.enabled, s.cron_expr, s.timezone, s.input_payload_json, s.last_run_at, s.next_run_at, s.last_error_text
from schedules s
join workflows w on w.id = s.workflow_id
where s.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by w.name;

select r.id, w.name as workflow_name, r.trigger, r.status, r.current_step_index, r.started_at, r.finished_at,
       left(r.error_text, 200) as error_text, r.input_payload_json
from runs r
left join workflows w on w.id = r.workflow_id
where r.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by coalesce(r.started_at, r.created_at) desc
limit 12;

select rs.run_id, rs.step_key, rs.step_kind, rs.status, rs.agent_config_id, rs.started_at, rs.finished_at,
       left(rs.input_json::text, 180) as input_json,
       left(rs.output_json::text, 180) as output_json
from run_steps rs
join runs r on r.id = rs.run_id
where r.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by coalesce(rs.started_at, rs.created_at) desc
limit 20;

select te.run_id, te.event_type, te.event_status, te.created_at,
       left(te.summary, 160) as summary,
       left(te.payload_json::text, 180) as payload_json
from trace_events te
where te.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by te.created_at desc
limit 25;

select count(*) as trade_proposals,
       count(*) filter (where status = 'APPROVED') as approved,
       count(*) filter (where status = 'EXECUTED') as executed_status
from trade_proposals
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select count(*) as trade_executions
from trade_executions
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select count(*) as positions_open
from positions
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
  and status = 'OPEN';

select count(*) as journals
from trade_journal
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select count(*) as news_events
from news_events
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select count(*) as market_snapshots
from market_snapshots
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select count(*) as agent_votes
from agent_votes
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586';

select rs.run_id, rs.step_key, rs.status, rs.started_at
from run_steps rs
join runs r on r.id = rs.run_id
where r.project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
  and rs.step_kind = 'exchange_execute'
order by rs.created_at desc
limit 10;

select id, proposal_id, exchange, symbol, side, execution_status, order_id, sl_order_id, tp_order_ids, created_at
from trade_executions
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by created_at desc
limit 10;

select name, provider, left(value_encrypted, 32) as value_encrypted_prefix, created_at, updated_at
from secrets
where project_id = '288bc95a-b4da-46e7-bdfa-b5630233f586'
order by name;


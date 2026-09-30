# Fleet Platform On-Call Runbook

## Scope

This runbook covers on-call for the Fleet Platform: Fleet Manager, telemetry ingestion, and the customer-facing fleet dashboard. Robot firmware issues are out of scope and belong to the Embedded team's rotation.

## Rotation and Escalation Policy

The rotation is weekly, Monday 09:00 to Monday 09:00, with a primary and a secondary on-call engineer. Handoff happens in the Monday platform standup.

Escalation proceeds in this order:

1. Primary on-call engineer: paged automatically by the alerting system, must acknowledge within 10 minutes.
2. Secondary on-call engineer: paged automatically if the primary has not acknowledged after 10 minutes.
3. Platform team lead: paged if neither primary nor secondary acknowledges within 25 minutes of the first page, or on request for any Sev 1.
4. VP of Engineering: informed by the team lead for any Sev 1 lasting longer than 60 minutes, or any incident with customer data exposure.

Sev 1 is defined as: a full Fleet Manager outage, any incident stopping robots at more than one customer site, or any suspected security breach. Sev 1 incidents require an incident channel, a designated incident commander, and customer communication within 60 minutes.

## First 15 Minutes

1. Acknowledge the page.
2. Open the fleet status dashboard and confirm blast radius: one site or many, one service or many.
3. Check the deployments feed: if a deploy landed in the last 2 hours, rollback is the default first action, investigation comes second.
4. If robots are physically stopped at a customer site, call the site supervisor using the contact sheet in the incident wiki. Stopped robots block aisles and pickers, minutes matter.

## Common Failures

- Telemetry ingestion lag: check the message queue depth first. If depth is growing, scale consumers before restarting anything, restarts lose in-flight batches.
- Dashboard 5xx errors: almost always the reporting database. Check connection pool saturation before failing over.
- Mass robot disconnects at one site: nearly always customer network changes, not our stack. Confirm with site IT before touching Fleet Manager.

## After the Incident

Every Sev 1 and Sev 2 gets a blameless postmortem within five business days, owned by the incident commander. Action items go into the platform backlog with an owner and a due date, not into a document nobody reads again.

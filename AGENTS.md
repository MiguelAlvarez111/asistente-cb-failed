# CB Failed Assistant Agent Notes

- Keep PHI out of AI payloads, logs, database records, audit records, feedback, and ordinary UI API responses.
- Never send `patientLast`, `patientFirst`, `DOB`, `AccNumber`, or `SIN` to AI.
- Uploaded files and full rows may exist only in temporary storage with TTL cleanup.
- Final actions must remain deterministic and rule-based; AI is only an ambiguous-comment interpreter.
- Dictionary type detection must be column/schema based, not filename based.
- Preserve useful behavior from the Streamlit MVP unless replacing it with an equivalent or stronger backend service.
- Run backend tests after backend changes and frontend build after UI changes when dependencies are available.
- After pushing code changes to GitHub, deploy the same commit to Railway and verify `/health` before reporting completion.

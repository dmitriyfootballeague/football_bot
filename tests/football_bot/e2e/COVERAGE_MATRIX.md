# Football Bot E2E Coverage Matrix

Legend:

| Marker | Meaning |
| --- | --- |
| `real` | Real aiogram dispatcher + live Postgres database |
| `fake` | Handler-level end-to-end flow with monkeypatched repositories/services |

## Suite Layout

| File | Scope |
| --- | --- |
| `support.py` | Shared real-e2e app harness, DB bootstrap, seed helpers, fixtures |
| `conftest.py` | Re-exported real-e2e fixtures |
| `test_real_e2e_registration_flows.py` | Registration, validation, `/help`, `/cancel`, pending restart |
| `test_real_e2e_user_info_flows.py` | Ratings and instruction flows |
| `test_real_e2e_transfer_flows.py` | Transfer happy paths, rejection paths, captain lists, edge cases |
| `test_real_e2e_admin_flows.py` | Admin edits and CSV export |
| `test_transfer_end_to_end_flows.py` | Fast handler-level transfer regression checks |

## Current Coverage

| Area | Scenario | Coverage | Test |
| --- | --- | --- | --- |
| Registration | Free-agent registration and admin approval | `real` | `test_real_e2e_registration_free_agent_approval` |
| Registration | Club registration rejection and in-place reapply | `real` | `test_real_e2e_registration_club_rejection_and_reapply` |
| Registration | Club player registration and admin approval | `real` | `test_real_e2e_registration_club_player_approval` |
| Registration | Club captain registration and admin approval | `real` | `test_real_e2e_registration_club_captain_approval` |
| Registration | Invalid name, surname, date, photo, plus `/help` and `/cancel` | `real` | `test_real_e2e_registration_validation_and_command_flows` |
| Registration | Pending user opens `/start` again | `real` | `test_real_e2e_registration_pending_user_reopens_start` |
| Rating | Approved player opens current rating | `real` | `test_real_e2e_rating_flows` |
| Rating | Approved free agent opens previous-season rating | `real` | `test_real_e2e_rating_flows` |
| Instructions | Guest opens instruction from `/start` | `real` | `test_real_e2e_instruction_flows` |
| Instructions | Approved user opens role-specific instruction | `real` | `test_real_e2e_instruction_flows` |
| Transfers | Join request list, captain approval, player confirmation, admin approval | `real` | `test_real_e2e_transfer_join_request_list_and_approval_flow` |
| Transfers | Exit request list, captain approval, admin approval | `real` | `test_real_e2e_transfer_exit_request_list_and_approval_flow` |
| Transfers | Captain invite, player opens invitations, player rejects | `real` | `test_real_e2e_transfer_invite_rejection_flow` |
| Transfers | Captain invite, player approves, captain confirms, admin rejects | `real` | `test_real_e2e_transfer_admin_reject_invite_flow` |
| Transfers | Admin rejects exit request | `real` | `test_real_e2e_transfer_admin_reject_exit_flow` |
| Transfers | Admin rejects join request | `real` | `test_real_e2e_transfer_admin_reject_join_flow` |
| Transfers | Captain kick request, admin approval | `real` | `test_real_e2e_transfer_kick_approve_flow` |
| Transfers | Captain kick request, admin rejection | `real` | `test_real_e2e_transfer_admin_reject_kick_flow` |
| Transfers | Edge cases: active request exists, same club selected | `real` | `test_real_e2e_transfer_edge_cases_active_request_and_same_club` |
| Transfers | Edge cases: no captain for exit/join | `real` | `test_real_e2e_transfer_edge_cases_missing_captain` |
| Transfers | Edge case: kick target is not in captain's club | `real` | `test_real_e2e_transfer_kick_player_not_in_club_edge_case` |
| Admin panel | Edit club name | `real` | `test_real_e2e_admin_panel_edit_flows` |
| Admin panel | Edit current rating | `real` | `test_real_e2e_admin_panel_edit_flows` |
| Admin panel | Edit previous-season rating | `real` | `test_real_e2e_admin_panel_edit_flows` |
| Admin panel | Export all scraped players CSV with ratings | `real` | `test_real_e2e_admin_export_all_players` |
| Transfers | Fast exit regression check | `fake` | `test_end_to_end_player_exit_flow` |
| Transfers | Fast join regression check | `fake` | `test_end_to_end_player_join_flow` |
| Transfers | Fast invite happy-path regression check | `fake` | `test_end_to_end_captain_invite_flow` |
| Transfers | Fast kick happy-path regression check | `fake` | `test_end_to_end_captain_kick_flow` |

## Remaining Gaps

None from the previous matrix. The real-e2e suite now covers every scenario that had been marked `gap`.

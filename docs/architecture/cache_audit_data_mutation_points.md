# Data Mutation Points (Service Layer)

Auto-generated from service write callsites and route mappings.
Review entries marked as internal/background for non-route callers.

| Entity | Service Method | File:Line | Route | Caches To Invalidate |
|---|---|---|---|---|
| DB | _managed_session | `backend/app/services/notification_provider.py:63` | internal/background | none known |
| DB | ensure_db_health | `backend/app/services/messaging/sse_stream.py:50` | internal/background | none known |
| User | AccountLifecycleService.deactivate_instructor_account | `backend/app/services/account_lifecycle_service.py:163` | POST /api/v1/account/deactivate | instructor:{id}:* (pattern), availability:instructor:{id}:* (pattern) |
| User | AccountLifecycleService.reactivate_instructor_account | `backend/app/services/account_lifecycle_service.py:209` | POST /api/v1/account/reactivate | instructor:{id}:* (pattern), availability:instructor:{id}:* (pattern) |
| User | AccountLifecycleService.suspend_instructor_account | `backend/app/services/account_lifecycle_service.py:112` | POST /api/v1/account/suspend | instructor:{id}:* (pattern), availability:instructor:{id}:* (pattern) |
| Address/ServiceArea | AddressService.create_address | `backend/app/services/address_service.py:201` | POST /api/v1/addresses/me | coverage:bulk*, neighborhoods:*, instructor:service_area_context:{id} |
| Address/ServiceArea | AddressService.delete_address | `backend/app/services/address_service.py:281` | DELETE /api/v1/addresses/me/{address_id} | coverage:bulk*, neighborhoods:*, instructor:service_area_context:{id} |
| ServiceArea/Address | AddressService.replace_service_areas | `backend/app/services/address_service.py:333` | PUT /api/v1/addresses/service-areas/me | coverage:bulk*, neighborhoods:*, instructor:service_area_context:{id} |
| Address/ServiceArea | AddressService.update_address | `backend/app/services/address_service.py:271` | PATCH /api/v1/addresses/me/{address_id} | coverage:bulk*, neighborhoods:*, instructor:service_area_context:{id} |
| LocationAlias/UnresolvedLocation | AliasLearningService._learn_from_row | `backend/app/services/search/alias_learning_service.py:136` | internal/background | none known |
| InstructorProfile/ServiceArea/User | AuthService.register_user | `backend/app/services/auth_service.py:103` | POST /api/v1/auth/register | auth_user:{email}, permissions:{user_id} |
| EventOutbox/Availability | AvailabilityService._enqueue_week_save_event | `backend/app/services/availability_service.py:575` | internal/background | avail:week*, avail:range*, avail:weekly* (if used), public_availability*, search:v* |
| Availability | AvailabilityService.add_blackout_date | `backend/app/services/availability_service.py:1639` | POST /api/v1/instructors/availability/blackout-dates | avail:week*, avail:range*, avail:weekly* (if used), public_availability*, search:v* |
| AvailabilityBitmap/Availability | AvailabilityService.add_specific_date_availability | `backend/app/services/availability_service.py:1587` | POST /api/v1/instructors/availability/specific-date | avail:week*, avail:range*, avail:weekly* (if used), public_availability*, search:v* |
| Availability | AvailabilityService.delete_blackout_date | `backend/app/services/availability_service.py:1662` | DELETE /api/v1/instructors/availability/blackout-dates/{blackout_id} | avail:week*, avail:range*, avail:weekly* (if used), public_availability*, search:v* |
| Availability | AvailabilityService.save_week_bits | `backend/app/services/availability_service.py:437` | POST /api/v1/instructors/availability/week | avail:week*, avail:range*, avail:weekly* (if used), public_availability*, search:v* |
| BackgroundCheck | BackgroundCheckService.invite | `backend/app/services/background_check_service.py:201` | POST /api/v1/instructors/{instructor_id}/bgc/invite; POST /api/v1/instructors/{instructor_id}/bgc/recheck | none known |
| BackgroundCheck | BackgroundCheckService.update_status_from_report | `backend/app/services/background_check_service.py:234` | internal/background | none known |
| DB/BackgroundCheck | BackgroundCheckWorkflowService._execute_final_adverse_action | `backend/app/services/background_check_workflow_service.py:695` | internal/background | none known |
| BackgroundCheck | BackgroundCheckWorkflowService._maybe_send_review_status_email | `backend/app/services/background_check_workflow_service.py:213` | internal/background | none known |
| BackgroundCheck | BackgroundCheckWorkflowService.handle_report_canceled | `backend/app/services/background_check_workflow_service.py:333` | POST /api/v1/webhooks/checkr | none known |
| BackgroundCheck | BackgroundCheckWorkflowService.handle_report_completed | `backend/app/services/background_check_workflow_service.py:252` | POST /api/v1/webhooks/checkr | none known |
| BackgroundCheck | BackgroundCheckWorkflowService.handle_report_eta_updated | `backend/app/services/background_check_workflow_service.py:389` | POST /api/v1/webhooks/checkr | none known |
| BackgroundCheck | BackgroundCheckWorkflowService.handle_report_suspended | `backend/app/services/background_check_workflow_service.py:309` | POST /api/v1/webhooks/checkr | none known |
| DB/BackgroundCheck | BackgroundCheckWorkflowService.resolve_dispute_and_resume_final_adverse | `backend/app/services/background_check_workflow_service.py:432` | internal/background | none known |
| BadgeAward | BadgeAdminService.confirm_award | `backend/app/services/badge_admin_service.py:60` | POST /api/v1/admin/badges/{award_id}/confirm | none known |
| BadgeAward | BadgeAdminService.revoke_award | `backend/app/services/badge_admin_service.py:69` | POST /api/v1/admin/badges/{award_id}/revoke | none known |
| BadgeAward | BadgeAwardService._award_according_to_hold | `backend/app/services/badge_award_service.py:207` | internal/background | none known |
| BadgeAward | BadgeAwardService._evaluate_consistent_learner | `backend/app/services/badge_award_service.py:715` | internal/background | none known |
| BadgeAward | BadgeAwardService._evaluate_explorer | `backend/app/services/badge_award_service.py:883` | internal/background | none known |
| BadgeAward | BadgeAwardService.backfill_user_badges | `backend/app/services/badge_award_service.py:425` | internal/background | none known |
| BadgeAward | BadgeAwardService.check_and_award_on_lesson_completed | `backend/app/services/badge_award_service.py:104` | internal/background | none known |
| BadgeAward | BadgeAwardService.finalize_pending_badges | `backend/app/services/badge_award_service.py:184` | internal/background | none known |
| DB | BaseService.transaction | `backend/app/services/base.py:145` | internal/background | none known |
| Booking | BookingService._create_booking_record | `backend/app/services/booking_service.py:2006` | internal/background | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Booking | BookingService._enqueue_booking_outbox_event | `backend/app/services/booking_service.py:195` | internal/background | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Booking | BookingService.abort_pending_booking | `backend/app/services/booking_service.py:2594` | POST /api/v1/bookings/{booking_id}/reschedule | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Payment/Booking | BookingService.cancel_booking | `backend/app/services/booking_service.py:998` | POST /api/v1/bookings/{booking_id}/cancel; POST /api/v1/bookings/{booking_id}/reschedule | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Payment/Booking | BookingService.confirm_booking_payment | `backend/app/services/booking_service.py:790` | PATCH /api/v1/bookings/{booking_id}/payment-method; POST /api/v1/bookings/{booking_id}/confirm-payment; POST /api/v1/bookings/{booking_id}/reschedule | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Payment/Booking | BookingService.create_booking_with_payment_setup | `backend/app/services/booking_service.py:614` | POST /api/v1/bookings; POST /api/v1/bookings/{booking_id}/reschedule | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Payment/Booking | BookingService.instructor_dispute_completion | `backend/app/services/booking_service.py:1581` | POST /api/v1/instructor-bookings/{booking_id}/dispute | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Payment/Booking | BookingService.instructor_mark_complete | `backend/app/services/booking_service.py:1504` | POST /api/v1/instructor-bookings/{booking_id}/complete | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Booking | BookingService.mark_no_show | `backend/app/services/booking_service.py:1649` | POST /api/v1/bookings/{booking_id}/no-show | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| Booking | BookingService.update_booking | `backend/app/services/booking_service.py:1326` | PATCH /api/v1/bookings/{booking_id} | booking_stats:instructor*, booking_stats:student*, avail:* (instructor/date), public_availability*, booking:get_* caches |
| DB/Config | ConfigService.commit | `backend/app/services/config_service.py:41` | internal/background | none known |
| Config | ConfigService.set_pricing_config | `backend/app/services/config_service.py:36` | internal/background | none known |
| Conversation/Message | ConversationService.create_conversation_with_message | `backend/app/services/conversation_service.py:606` | POST /api/v1/conversations | none known |
| Conversation/Message | ConversationService.get_or_create_conversation | `backend/app/services/conversation_service.py:145` | internal/background | none known |
| Conversation/ConversationState/Message | ConversationService.send_message | `backend/app/services/conversation_service.py:352` | internal/background | none known |
| Conversation/ConversationState/Message | ConversationService.send_message_with_context | `backend/app/services/conversation_service.py:816` | POST /api/v1/conversations/{conversation_id}/messages | none known |
| ConversationState/Conversation/Message | ConversationService.set_conversation_user_state | `backend/app/services/conversation_service.py:230` | PUT /api/v1/conversations/{conversation_id}/state | none known |
| Favorite | FavoritesService.add_favorite | `backend/app/services/favorites_service.py:88` | POST /api/v1/favorites/{instructor_id} | favorites:{student_id}:{instructor_id}, favorites:list:{student_id} |
| Favorite | FavoritesService.remove_favorite | `backend/app/services/favorites_service.py:137` | DELETE /api/v1/favorites/{instructor_id} | favorites:{student_id}:{instructor_id}, favorites:list:{student_id} |
| ServiceAnalytics/InstructorProfile/InstructorService | InstructorService._get_service_analytics | `backend/app/services/instructor_service.py:1323` | internal/background | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| PreferredPlace/InstructorProfile/InstructorService | InstructorService._replace_preferred_places | `backend/app/services/instructor_service.py:765` | internal/background | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorProfile/InstructorService | InstructorService._update_services | `backend/app/services/instructor_service.py:695` | internal/background | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorProfile/InstructorService/User | InstructorService.create_instructor_profile | `backend/app/services/instructor_service.py:346` | POST /api/v1/instructors/me | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorService/InstructorProfile | InstructorService.create_instructor_service_from_catalog | `backend/app/services/instructor_service.py:1097` | POST /api/v1/services/instructor/add | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorProfile/InstructorService | InstructorService.delete_instructor_profile | `backend/app/services/instructor_service.py:532` | DELETE /api/v1/instructors/me | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| ServiceAnalytics/InstructorProfile/InstructorService | InstructorService.get_all_services_with_instructors | `backend/app/services/instructor_service.py:1492` | GET /api/v1/services/catalog/all-with-instructors | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| ServiceAnalytics/InstructorProfile/InstructorService | InstructorService.get_top_services_per_category | `backend/app/services/instructor_service.py:1409` | GET /api/v1/services/catalog/top-per-category | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorProfile/InstructorService | InstructorService.go_live | `backend/app/services/instructor_service.py:612` | POST /api/v1/instructors/me/go-live | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| ServiceAnalytics/InstructorProfile/InstructorService | InstructorService.search_services_enhanced | `backend/app/services/instructor_service.py:1303` | internal/background | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| ServiceAnalytics/InstructorProfile/InstructorService | InstructorService.search_services_semantic | `backend/app/services/instructor_service.py:1188` | internal/background | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| InstructorProfile/InstructorService | InstructorService.update_instructor_profile | `backend/app/services/instructor_service.py:478` | PUT /api/v1/instructors/me | instructor:public*, catalog:* (services/categories/top/all/kids), service_catalog:* (legacy), avail:* (invalidate_instructor_availability), search:v* |
| LocationAlias/UnresolvedLocation | LocationLearningAdminService.create_manual_alias | `backend/app/services/search/location_learning_admin_service.py:248` | internal/background | none known |
| UnresolvedLocation/LocationAlias | LocationLearningAdminService.dismiss_unresolved | `backend/app/services/search/location_learning_admin_service.py:192` | internal/background | none known |
| LocationAlias | LocationLearningAdminService.set_alias_status | `backend/app/services/search/location_learning_admin_service.py:159` | internal/background | none known |
| UnresolvedLocation | LocationLearningClickService.capture_location_learning_click | `backend/app/services/search/location_learning_click_service.py:54` | internal/background | none known |
| DB/LocationAlias | LocationResolver._cache_llm_alias | `backend/app/services/search/location_resolver.py:823` | internal/background | none known |
| LocationAlias | LocationResolver._load_cached | `backend/app/services/search/location_resolver.py:728` | internal/background | none known |
| LocationAlias | LocationResolver._tier2_alias_lookup | `backend/app/services/search/location_resolver.py:502` | internal/background | none known |
| DB/LocationAlias | LocationResolver.cache_llm_alias | `backend/app/services/search/location_resolver.py:894` | internal/background | none known |
| Message | MessageService.add_reaction | `backend/app/services/message_service.py:268` | internal/background | none known |
| Message | MessageService.add_reaction_with_context | `backend/app/services/message_service.py:571` | POST /api/v1/messages/{message_id}/reactions | none known |
| Message | MessageService.delete_message | `backend/app/services/message_service.py:245` | internal/background | none known |
| Message | MessageService.delete_message_with_context | `backend/app/services/message_service.py:543` | DELETE /api/v1/messages/{message_id} | none known |
| Message | MessageService.edit_message | `backend/app/services/message_service.py:346` | internal/background | none known |
| Message | MessageService.edit_message_with_context | `backend/app/services/message_service.py:497` | PATCH /api/v1/messages/{message_id} | none known |
| Message | MessageService.mark_messages_as_read | `backend/app/services/message_service.py:183` | internal/background | none known |
| Message | MessageService.mark_messages_read_with_context | `backend/app/services/message_service.py:421` | POST /api/v1/messages/mark-read | none known |
| Message | MessageService.remove_reaction | `backend/app/services/message_service.py:302` | internal/background | none known |
| Message | MessageService.remove_reaction_with_context | `backend/app/services/message_service.py:607` | DELETE /api/v1/messages/{message_id}/reactions | none known |
| LocationAlias | NLSearchService._run_post_openai_burst | `backend/app/services/search/nl_search_service.py:2020` | internal/background | none known |
| EventOutbox/NotificationDelivery | NotificationProvider.send | `backend/app/services/notification_provider.py:140` | internal/background | none known |
| PasswordResetToken | PasswordResetService._generate_reset_token | `backend/app/services/password_reset_service.py:221` | internal/background | none known |
| PasswordResetToken | PasswordResetService._invalidate_existing_tokens | `backend/app/services/password_reset_service.py:242` | internal/background | none known |
| PasswordResetToken/User | PasswordResetService.confirm_password_reset | `backend/app/services/password_reset_service.py:188` | POST /api/v1/password-reset/confirm | none known |
| DB/Permission/RBAC | PermissionService.assign_role | `backend/app/services/permission_service.py:310` | internal/background | permissions:{user_id} |
| DB/RBAC/Permission | PermissionService.grant_permission | `backend/app/services/permission_service.py:234` | internal/background | permissions:{user_id} |
| DB/Permission/RBAC | PermissionService.remove_role | `backend/app/services/permission_service.py:343` | internal/background | permissions:{user_id} |
| DB/RBAC/Permission | PermissionService.revoke_permission | `backend/app/services/permission_service.py:272` | internal/background | permissions:{user_id} |
| UserProfilePicture | PersonalAssetService.finalize_profile_picture | `backend/app/services/personal_asset_service.py:276` | POST /api/v1/uploads/r2/finalize/profile-picture; POST /api/v1/users/me/profile-picture | profile_pic_url:{user_id}:*, instructor:public* (profile photo), auth_user:{email} |
| DB/SearchEvent/SearchHistory/User | PrivacyService.anonymize_user | `backend/app/services/privacy_service.py:387` | internal/background | none known |
| DB/SearchEvent/User/SearchHistory | PrivacyService.apply_retention_policies | `backend/app/services/privacy_service.py:301` | internal/background | none known |
| DB/InstructorProfile/SearchEvent/SearchHistory/User | PrivacyService.delete_user_data | `backend/app/services/privacy_service.py:217` | internal/background | none known |
| ReferralLimit/Referral | ReferralService._is_velocity_abuse | `backend/app/services/referral_service.py:517` | internal/background | none known |
| ReferralAttribution/ReferralClick/Referral | ReferralService.attribute_signup | `backend/app/services/referral_service.py:199` | POST /api/v1/admin/referrals/claim | none known |
| ReferralReward/Referral | ReferralService.on_first_booking_completed | `backend/app/services/referral_service.py:277` | internal/background | none known |
| ReferralReward/Referral | ReferralService.on_instructor_lesson_completed | `backend/app/services/referral_service.py:345` | internal/background | none known |
| ReferralClick/Referral | ReferralService.record_click | `backend/app/services/referral_service.py:155` | internal/background | none known |
| ReferralReward | ReferralUnlocker.run | `backend/app/services/referral_unlocker.py:95` | internal/background | none known |
| RetentionDelete | RetentionService._purge_table_chunks | `backend/app/services/retention_service.py:263` | internal/background | none known |
| DB | RetentionService.purge_availability_days | `backend/app/services/retention_service.py:360` | internal/background | none known |
| ReviewResponse/Review/Tip | ReviewService.add_instructor_response | `backend/app/services/review_service.py:558` | POST /api/v1/reviews/{review_id}/respond | ratings:* (versioned + legacy), search:v* |
| Tip/Review/ReviewResponse | ReviewService.submit_review | `backend/app/services/review_service.py:208` | internal/background | ratings:* (versioned + legacy), search:v* |
| Tip/Review/ReviewResponse | ReviewService.submit_review_with_tip | `backend/app/services/review_service.py:315` | POST /api/v1/reviews | ratings:* (versioned + legacy), search:v* |
| SearchHistory | SearchHistoryCleanupService.cleanup_old_guest_sessions | `backend/app/services/search_history_cleanup_service.py:98` | internal/background | none known |
| SearchHistory | SearchHistoryCleanupService.cleanup_soft_deleted_searches | `backend/app/services/search_history_cleanup_service.py:57` | internal/background | none known |
| SearchHistory | SearchHistoryService.convert_guest_searches_to_user | `backend/app/services/search_history_service.py:444` | internal/background | none known |
| SearchHistory | SearchHistoryService.delete_search | `backend/app/services/search_history_service.py:362` | internal/background | none known |
| SearchInteraction/SearchHistory | SearchHistoryService.track_interaction | `backend/app/services/search_history_service.py:532` | internal/background | none known |
| Payment/Booking | StripeService._handle_account_webhook | `backend/app/services/stripe_service.py:3001` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService._handle_charge_webhook | `backend/app/services/stripe_service.py:3075` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| InstructorProfile/Payment/Booking | StripeService._handle_identity_webhook | `backend/app/services/stripe_service.py:3235` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService._handle_payout_webhook | `backend/app/services/stripe_service.py:3143` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Booking/Payment | StripeService._handle_successful_payment | `backend/app/services/stripe_service.py:2970` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService._persist_connected_account | `backend/app/services/stripe_service.py:1782` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.build_charge_context | `backend/app/services/stripe_service.py:1499` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.cancel_payment_intent | `backend/app/services/stripe_service.py:2460` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.capture_payment_intent | `backend/app/services/stripe_service.py:2355` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.check_account_status | `backend/app/services/stripe_service.py:2019` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.confirm_payment_intent | `backend/app/services/stripe_service.py:2308` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.create_and_confirm_manual_authorization | `backend/app/services/stripe_service.py:2262` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Booking/Payment | StripeService.create_booking_checkout | `backend/app/services/stripe_service.py:494` | POST /api/v1/payments/checkout | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.create_customer | `backend/app/services/stripe_service.py:1679` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.create_or_retry_booking_payment_intent | `backend/app/services/stripe_service.py:1298` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.create_payment_intent | `backend/app/services/stripe_service.py:2166` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.delete_payment_method | `backend/app/services/stripe_service.py:2752` | DELETE /api/v1/payments/methods/{method_id} | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.ensure_top_up_transfer | `backend/app/services/stripe_service.py:1194` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.handle_payment_intent_webhook | `backend/app/services/stripe_service.py:2930` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.process_booking_payment | `backend/app/services/stripe_service.py:2523` | internal/background | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| InstructorProfile/Payment/Booking | StripeService.refresh_instructor_identity | `backend/app/services/stripe_service.py:337` | POST /api/v1/payments/identity/refresh | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Booking | StripeService.save_payment_method | `backend/app/services/stripe_service.py:2637` | POST /api/v1/payments/methods | booking_stats*, avail:* (if booking status changes), instructor:public* (if identity status changes) |
| Payment/Credit | StudentCreditService.issue_milestone_credit | `backend/app/services/student_credit_service.py:101` | internal/background | none known |
| Payment/Credit | StudentCreditService.reinstate_used_credits | `backend/app/services/student_credit_service.py:180` | internal/background | none known |
| Payment/Credit | StudentCreditService.revoke_milestone_credit | `backend/app/services/student_credit_service.py:127` | internal/background | none known |
| Conversation/Message | SystemMessageService._create_system_message | `backend/app/services/system_message_service.py:351` | internal/background | none known |
| Conversation/Message | SystemMessageService._get_or_create_conversation | `backend/app/services/system_message_service.py:276` | internal/background | none known |
| ReferralReward/WalletTransaction | WalletService.apply_fee_rebate_on_payout | `backend/app/services/wallet_service.py:60` | internal/background | none known |
| ReferralReward/WalletTransaction | WalletService.consume_student_credit | `backend/app/services/wallet_service.py:96` | internal/background | none known |
| EventOutbox/Availability | WeekOperationService._enqueue_week_copy_event | `backend/app/services/week_operation_service.py:369` | internal/background | avail:week*, avail:range*, public_availability*, search:v* |
| Availability | WeekOperationService.copy_week_availability | `backend/app/services/week_operation_service.py:177` | POST /api/v1/instructors/availability/copy-week | avail:week*, avail:range*, public_availability*, search:v* |

export type paths = {
 "/api/v1/2fa/disable": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["disable_api_v1_2fa_disable_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/2fa/regenerate-backup-codes": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["regenerate_backup_codes_api_v1_2fa_regenerate_backup_codes_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/2fa/setup/initiate": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["setup_initiate_api_v1_2fa_setup_initiate_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/2fa/setup/verify": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["setup_verify_api_v1_2fa_setup_verify_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/2fa/status": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["status_endpoint_api_v1_2fa_status_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/2fa/verify-login": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["verify_login_api_v1_2fa_verify_login_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/deactivate": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["deactivate_account_api_v1_account_deactivate_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/phone": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_phone_number_api_v1_account_phone_get"];
 put: operations["update_phone_number_api_v1_account_phone_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/phone/verify": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_phone_verification_api_v1_account_phone_verify_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/phone/verify/confirm": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["confirm_phone_verification_api_v1_account_phone_verify_confirm_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/reactivate": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reactivate_account_api_v1_account_reactivate_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/status": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["check_account_status_api_v1_account_status_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/account/suspend": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["suspend_account_api_v1_account_suspend_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/coverage/bulk": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_bulk_coverage_geojson_api_v1_addresses_coverage_bulk_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_my_addresses_api_v1_addresses_me_get"];
 put?: never;
 post: operations["create_my_address_api_v1_addresses_me_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/me/{address_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_my_address_api_v1_addresses_me__address_id__delete"];
 options?: never;
 head?: never;
 patch: operations["update_my_address_api_v1_addresses_me__address_id__patch"];
 trace?: never;
 };
 "/api/v1/addresses/places/autocomplete": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["places_autocomplete_api_v1_addresses_places_autocomplete_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/places/details": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["place_details_api_v1_addresses_places_details_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/regions/neighborhoods": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_neighborhoods_api_v1_addresses_regions_neighborhoods_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/service-areas/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_my_service_areas_api_v1_addresses_service_areas_me_get"];
 put: operations["replace_my_service_areas_api_v1_addresses_service_areas_me_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/addresses/zip/is-nyc": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["is_nyc_zip_api_v1_addresses_zip_is_nyc_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/audit": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_audit_logs_api_v1_admin_audit_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/audit-log": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_admin_audit_log_api_v1_admin_audit_log_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/cases": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_cases_api_v1_admin_background_checks_cases_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/consent/{instructor_id}/latest": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["admin_latest_consent_api_v1_admin_background_checks_consent__instructor_id__latest_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/counts": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_counts_api_v1_admin_background_checks_counts_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/expiring": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_expiring_api_v1_admin_background_checks_expiring_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/history/{instructor_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_history_api_v1_admin_background_checks_history__instructor_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/review": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_review_list_api_v1_admin_background_checks_review_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/review/count": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_review_count_api_v1_admin_background_checks_review_count_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/webhooks": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_webhook_logs_api_v1_admin_background_checks_webhooks_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/webhooks/stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["bgc_webhook_stats_api_v1_admin_background_checks_webhooks_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/{instructor_id}/dispute/open": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["open_bgc_dispute_api_v1_admin_background_checks__instructor_id__dispute_open_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/{instructor_id}/dispute/resolve": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["resolve_bgc_dispute_api_v1_admin_background_checks__instructor_id__dispute_resolve_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/background-checks/{instructor_id}/override": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["bgc_review_override_api_v1_admin_background_checks__instructor_id__override_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/badges/pending": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_pending_awards_api_v1_admin_badges_pending_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/badges/{award_id}/confirm": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["confirm_award_api_v1_admin_badges__award_id__confirm_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/badges/{award_id}/revoke": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["revoke_award_api_v1_admin_badges__award_id__revoke_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_admin_bookings_api_v1_admin_bookings_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_admin_booking_stats_api_v1_admin_bookings_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/{booking_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_admin_booking_detail_api_v1_admin_bookings__booking_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/{booking_id}/cancel": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["admin_cancel_booking_api_v1_admin_bookings__booking_id__cancel_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/{booking_id}/complete": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["admin_update_booking_status_api_v1_admin_bookings__booking_id__complete_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/{booking_id}/no-show/resolve": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["resolve_no_show_api_v1_admin_bookings__booking_id__no_show_resolve_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/bookings/{booking_id}/refund": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["admin_refund_booking_api_v1_admin_bookings__booking_id__refund_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/config/pricing": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_pricing_config_api_v1_admin_config_pricing_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch: operations["update_pricing_config_api_v1_admin_config_pricing_patch"];
 trace?: never;
 };
 "/api/v1/admin/instructors/founding/count": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["founding_instructor_count_api_v1_admin_instructors_founding_count_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/instructors/{instructor_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["admin_instructor_detail_api_v1_admin_instructors__instructor_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/referrals/config": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_referral_config_api_v1_admin_referrals_config_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/referrals/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_referral_health_api_v1_admin_referrals_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/referrals/summary": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_referral_summary_api_v1_admin_referrals_summary_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/search-config": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_config_admin_api_v1_admin_search_config_get"];
 put?: never;
 post: operations["update_search_config_admin_api_v1_admin_search_config_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/admin/search-config/reset": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reset_search_config_admin_api_v1_admin_search_config_reset_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/codebase/history": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_codebase_metrics_history_api_v1_analytics_codebase_history_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/codebase/history/append": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["append_codebase_metrics_history_api_v1_analytics_codebase_history_append_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/codebase/metrics": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_codebase_metrics_api_v1_analytics_codebase_metrics_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/export": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["export_analytics_api_v1_analytics_export_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/candidates/category-trends": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["candidates_category_trends_api_v1_analytics_search_candidates_category_trends_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/candidates/queries": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["candidate_service_queries_api_v1_analytics_search_candidates_queries_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/candidates/score-distribution": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["candidates_score_distribution_api_v1_analytics_search_candidates_score_distribution_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/candidates/summary": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["candidates_summary_api_v1_analytics_search_candidates_summary_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/candidates/top-services": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["candidates_top_services_api_v1_analytics_search_candidates_top_services_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/conversion-metrics": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_conversion_metrics_api_v1_analytics_search_conversion_metrics_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/popular-searches": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_popular_searches_api_v1_analytics_search_popular_searches_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/referrers": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_referrers_api_v1_analytics_search_referrers_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/search-analytics-summary": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_analytics_summary_api_v1_analytics_search_search_analytics_summary_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/search-performance": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_performance_api_v1_analytics_search_search_performance_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/analytics/search/search-trends": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_trends_api_v1_analytics_search_search_trends_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/auth/change-password": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["change_password_api_v1_auth_change_password_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/auth/login": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["login_api_v1_auth_login_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/auth/login-with-session": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["login_with_session_api_v1_auth_login_with_session_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/auth/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["read_users_me_api_v1_auth_me_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch: operations["update_current_user_api_v1_auth_me_patch"];
 trace?: never;
 };
 "/api/v1/auth/register": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["register_api_v1_auth_register_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/consume": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["consume_invite_api_v1_beta_invites_consume_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/generate": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["generate_invites_api_v1_beta_invites_generate_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/send": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_invite_api_v1_beta_invites_send_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/send-batch": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_invite_batch_api_v1_beta_invites_send_batch_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/send-batch-async": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_invite_batch_async_api_v1_beta_invites_send_batch_async_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/send-batch-progress": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_invite_batch_progress_api_v1_beta_invites_send_batch_progress_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/validate": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["validate_invite_api_v1_beta_invites_validate_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/invites/verified": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["invite_verified_api_v1_beta_invites_verified_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/metrics/summary": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_beta_metrics_summary_api_v1_beta_metrics_summary_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/beta/settings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_beta_settings_api_v1_beta_settings_get"];
 put: operations["update_beta_settings_api_v1_beta_settings_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_bookings_api_v1_bookings_get"];
 put?: never;
 post: operations["create_booking_api_v1_bookings_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/check-availability": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["check_availability_api_v1_bookings_check_availability_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/send-reminders": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_reminder_emails_api_v1_bookings_send_reminders_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_booking_stats_api_v1_bookings_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/upcoming": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_upcoming_bookings_api_v1_bookings_upcoming_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_booking_details_api_v1_bookings__booking_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch: operations["update_booking_api_v1_bookings__booking_id__patch"];
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/cancel": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["cancel_booking_api_v1_bookings__booking_id__cancel_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/complete": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["complete_booking_api_v1_bookings__booking_id__complete_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/confirm-payment": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["confirm_booking_payment_api_v1_bookings__booking_id__confirm_payment_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/no-show": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["report_no_show_api_v1_bookings__booking_id__no_show_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/no-show/dispute": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["dispute_no_show_api_v1_bookings__booking_id__no_show_dispute_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/payment-method": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch: operations["update_booking_payment_method_api_v1_bookings__booking_id__payment_method_patch"];
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/preview": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_booking_preview_api_v1_bookings__booking_id__preview_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/pricing": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_booking_pricing_api_v1_bookings__booking_id__pricing_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/reschedule": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reschedule_booking_api_v1_bookings__booking_id__reschedule_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/bookings/{booking_id}/retry-payment": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["retry_payment_authorization_api_v1_bookings__booking_id__retry_payment_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/config/pricing": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_public_pricing_config_api_v1_config_pricing_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/config/public": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_public_config_api_v1_config_public_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/conversations": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_conversations_api_v1_conversations_get"];
 put?: never;
 post: operations["create_conversation_api_v1_conversations_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/conversations/{conversation_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_conversation_api_v1_conversations__conversation_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/conversations/{conversation_id}/messages": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_messages_api_v1_conversations__conversation_id__messages_get"];
 put?: never;
 post: operations["send_message_api_v1_conversations__conversation_id__messages_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/conversations/{conversation_id}/state": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put: operations["update_conversation_state_api_v1_conversations__conversation_id__state_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/conversations/{conversation_id}/typing": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_typing_indicator_api_v1_conversations__conversation_id__typing_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/database/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["database_health_api_v1_database_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/database/pool-status": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["database_pool_status_api_v1_database_pool_status_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/database/stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["database_stats_api_v1_database_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/favorites": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_favorites_api_v1_favorites_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/favorites/check/{instructor_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["check_favorite_status_api_v1_favorites_check__instructor_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/favorites/{instructor_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["add_favorite_api_v1_favorites__instructor_id__post"];
 delete: operations["remove_favorite_api_v1_favorites__instructor_id__delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/gated/ping": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["gated_ping_api_v1_gated_ping_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["health_check_api_v1_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/health/lite": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["health_check_lite_api_v1_health_lite_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/health/rate-limit-test": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["rate_limit_test_api_v1_health_rate_limit_test_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_instructor_bookings_api_v1_instructor_bookings_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings/completed": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_completed_bookings_api_v1_instructor_bookings_completed_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings/pending-completion": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_pending_completion_bookings_api_v1_instructor_bookings_pending_completion_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings/upcoming": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_upcoming_bookings_api_v1_instructor_bookings_upcoming_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings/{booking_id}/complete": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mark_lesson_complete_api_v1_instructor_bookings__booking_id__complete_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructor-bookings/{booking_id}/dispute": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["dispute_completion_api_v1_instructor_bookings__booking_id__dispute_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_instructors_api_v1_instructors_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_all_availability_api_v1_instructors_availability_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/apply-to-date-range": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["apply_to_date_range_api_v1_instructors_availability_apply_to_date_range_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/blackout-dates": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_blackout_dates_api_v1_instructors_availability_blackout_dates_get"];
 put?: never;
 post: operations["add_blackout_date_api_v1_instructors_availability_blackout_dates_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/blackout-dates/{blackout_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_blackout_date_api_v1_instructors_availability_blackout_dates__blackout_id__delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/bulk-update": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch: operations["bulk_update_availability_api_v1_instructors_availability_bulk_update_patch"];
 trace?: never;
 };
 "/api/v1/instructors/availability/copy-week": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["copy_week_availability_api_v1_instructors_availability_copy_week_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/specific-date": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["add_specific_date_availability_api_v1_instructors_availability_specific_date_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/week": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_week_availability_api_v1_instructors_availability_week_get"];
 put?: never;
 post: operations["save_week_availability_api_v1_instructors_availability_week_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/week/booked-slots": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_week_booked_slots_api_v1_instructors_availability_week_booked_slots_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/week/validate-changes": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["validate_week_changes_api_v1_instructors_availability_week_validate_changes_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/availability/{window_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_availability_window_api_v1_instructors_availability__window_id__delete"];
 options?: never;
 head?: never;
 patch: operations["update_availability_window_api_v1_instructors_availability__window_id__patch"];
 trace?: never;
 };
 "/api/v1/instructors/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_my_profile_api_v1_instructors_me_get"];
 put: operations["update_profile_api_v1_instructors_me_put"];
 post: operations["create_profile_api_v1_instructors_me_post"];
 delete: operations["delete_profile_api_v1_instructors_me_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/me/go-live": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["go_live_api_v1_instructors_me_go_live_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_instructor_api_v1_instructors__instructor_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/consent": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["record_background_check_consent_api_v1_instructors__instructor_id__bgc_consent_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/invite": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["trigger_background_check_invite_api_v1_instructors__instructor_id__bgc_invite_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/mock/pass": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mock_background_check_pass_api_v1_instructors__instructor_id__bgc_mock_pass_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/mock/reset": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mock_background_check_reset_api_v1_instructors__instructor_id__bgc_mock_reset_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/mock/review": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mock_background_check_review_api_v1_instructors__instructor_id__bgc_mock_review_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/recheck": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["trigger_background_check_recheck_api_v1_instructors__instructor_id__bgc_recheck_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/bgc/status": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_background_check_status_api_v1_instructors__instructor_id__bgc_status_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/instructors/{instructor_id}/coverage": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_coverage_api_v1_instructors__instructor_id__coverage_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/messages/config": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_message_config_api_v1_messages_config_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/messages/mark-read": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mark_messages_as_read_api_v1_messages_mark_read_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/messages/stream": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["stream_user_messages_api_v1_messages_stream_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/messages/unread-count": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_unread_count_api_v1_messages_unread_count_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/messages/{message_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_message_api_v1_messages__message_id__delete"];
 options?: never;
 head?: never;
 patch: operations["edit_message_api_v1_messages__message_id__patch"];
 trace?: never;
 };
 "/api/v1/messages/{message_id}/reactions": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["add_reaction_api_v1_messages__message_id__reactions_post"];
 delete: operations["remove_reaction_api_v1_messages__message_id__reactions_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/alerts/acknowledge/{alert_type}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["acknowledge_alert_api_v1_monitoring_alerts_acknowledge__alert_type__post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/alerts/live": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_live_alerts_api_v1_monitoring_alerts_live_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/alerts/recent": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_recent_alerts_api_v1_monitoring_alerts_recent_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/alerts/summary": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_alert_summary_api_v1_monitoring_alerts_summary_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/cache/extended-stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_extended_cache_stats_api_v1_monitoring_cache_extended_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/dashboard": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_monitoring_dashboard_api_v1_monitoring_dashboard_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/payment-health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_payment_system_health_api_v1_monitoring_payment_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/slow-queries": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_slow_queries_api_v1_monitoring_slow_queries_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/slow-requests": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_slow_requests_api_v1_monitoring_slow_requests_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/monitoring/trigger-payment-health-check": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["trigger_payment_health_check_api_v1_monitoring_trigger_payment_health_check_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notification-preferences": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_preferences_api_v1_notification_preferences_get"];
 put: operations["update_preferences_bulk_api_v1_notification_preferences_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notification-preferences/{category}/{channel}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put: operations["update_preference_api_v1_notification_preferences__category___channel__put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notifications": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_notifications_api_v1_notifications_get"];
 put?: never;
 post?: never;
 delete: operations["delete_all_notifications_api_v1_notifications_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notifications/read-all": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mark_all_notifications_read_api_v1_notifications_read_all_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notifications/unread-count": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_unread_count_api_v1_notifications_unread_count_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notifications/{notification_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_notification_api_v1_notifications__notification_id__delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/notifications/{notification_id}/read": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["mark_notification_read_api_v1_notifications__notification_id__read_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/cache": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_cache_metrics_api_v1_ops_cache_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/cache/availability": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_availability_cache_metrics_api_v1_ops_cache_availability_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/cache/reset-stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reset_cache_stats_api_v1_ops_cache_reset_stats_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["health_check_api_v1_ops_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/performance": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_performance_metrics_api_v1_ops_performance_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/rate-limits": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_rate_limit_stats_api_v1_ops_rate_limits_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/rate-limits/reset": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reset_rate_limits_api_v1_ops_rate_limits_reset_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/rate-limits/test": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["test_rate_limit_api_v1_ops_rate_limits_test_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ops/slow-queries": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_slow_queries_api_v1_ops_slow_queries_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/password-reset/confirm": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["confirm_password_reset_api_v1_password_reset_confirm_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/password-reset/request": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["request_password_reset_api_v1_password_reset_request_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/password-reset/verify/{token}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["verify_reset_token_api_v1_password_reset_verify__token__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/checkout": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["create_checkout_api_v1_payments_checkout_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/connect/dashboard": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_dashboard_link_api_v1_payments_connect_dashboard_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/connect/instant-payout": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["request_instant_payout_api_v1_payments_connect_instant_payout_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/connect/onboard": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["start_onboarding_api_v1_payments_connect_onboard_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/connect/payout-schedule": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["set_payout_schedule_api_v1_payments_connect_payout_schedule_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/connect/status": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_onboarding_status_api_v1_payments_connect_status_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/credits": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_credit_balance_api_v1_payments_credits_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/earnings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_instructor_earnings_api_v1_payments_earnings_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/earnings/export": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["export_instructor_earnings_api_v1_payments_earnings_export_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/identity/refresh": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["refresh_identity_status_api_v1_payments_identity_refresh_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/identity/session": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["create_identity_session_api_v1_payments_identity_session_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/methods": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_payment_methods_api_v1_payments_methods_get"];
 put?: never;
 post: operations["save_payment_method_api_v1_payments_methods_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/methods/{method_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_payment_method_api_v1_payments_methods__method_id__delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/payouts": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_instructor_payouts_api_v1_payments_payouts_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/transactions": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_transaction_history_api_v1_payments_transactions_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/payments/webhooks/stripe": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["handle_stripe_webhook_api_v1_payments_webhooks_stripe_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/pricing/preview": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["preview_selection_pricing_api_v1_pricing_preview_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/delete/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["delete_my_data_api_v1_privacy_delete_me_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/delete/user/{user_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["delete_user_data_admin_api_v1_privacy_delete_user__user_id__post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/export/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["export_my_data_api_v1_privacy_export_me_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/export/user/{user_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["export_user_data_admin_api_v1_privacy_export_user__user_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/retention/apply": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["apply_retention_policies_api_v1_privacy_retention_apply_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/privacy/statistics": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_privacy_statistics_api_v1_privacy_statistics_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/public/instructors/{instructor_id}/availability": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_instructor_public_availability_api_v1_public_instructors__instructor_id__availability_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/public/instructors/{instructor_id}/next-available": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_next_available_slot_api_v1_public_instructors__instructor_id__next_available_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/public/logout": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["public_logout_api_v1_public_logout_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/public/referrals/send": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["send_referral_invites_api_v1_public_referrals_send_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/public/session/guest": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["create_guest_session_api_v1_public_session_guest_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/push/subscribe": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["subscribe_to_push_api_v1_push_subscribe_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/push/subscriptions": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_subscriptions_api_v1_push_subscriptions_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/push/unsubscribe": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["unsubscribe_from_push_api_v1_push_unsubscribe_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/push/vapid-public-key": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_vapid_public_key_api_v1_push_vapid_public_key_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/r/{slug}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["resolve_referral_slug_api_v1_r__slug__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/ready": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["ready_probe_api_v1_ready_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/celery-queues": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["celery_queue_status_api_v1_redis_celery_queues_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/connection-audit": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["redis_connection_audit_api_v1_redis_connection_audit_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/flush-queues": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["flush_celery_queues_api_v1_redis_flush_queues_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["redis_health_api_v1_redis_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/stats": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["redis_stats_api_v1_redis_stats_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/redis/test": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["redis_test_api_v1_redis_test_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/referrals/checkout/apply-referral": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["apply_referral_credit_api_v1_referrals_checkout_apply_referral_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/referrals/claim": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["claim_referral_code_api_v1_referrals_claim_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/referrals/me": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_my_referral_ledger_api_v1_referrals_me_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["submit_review_api_v1_reviews_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/booking/existing": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["get_existing_reviews_for_bookings_api_v1_reviews_booking_existing_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/booking/{booking_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_review_for_booking_api_v1_reviews_booking__booking_id__get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/instructor/{instructor_id}/ratings": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_instructor_ratings_api_v1_reviews_instructor__instructor_id__ratings_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/instructor/{instructor_id}/recent": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_recent_reviews_api_v1_reviews_instructor__instructor_id__recent_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/instructor/{instructor_id}/search-rating": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_search_rating_api_v1_reviews_instructor__instructor_id__search_rating_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/ratings/batch": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["get_ratings_batch_api_v1_reviews_ratings_batch_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/reviews/{review_id}/respond": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["respond_to_review_api_v1_reviews__review_id__respond_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["nl_search_api_v1_search_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search-history": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_recent_searches_api_v1_search_history_get"];
 put?: never;
 post: operations["record_search_api_v1_search_history_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search-history/guest": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["record_guest_search_api_v1_search_history_guest_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search-history/interaction": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["track_interaction_api_v1_search_history_interaction_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search-history/{search_id}": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post?: never;
 delete: operations["delete_search_api_v1_search_history__search_id__delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/analytics/metrics": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["search_metrics_api_v1_search_analytics_metrics_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/analytics/popular": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["popular_queries_api_v1_search_analytics_popular_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/analytics/zero-results": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["zero_result_queries_api_v1_search_analytics_zero_results_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/click": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["log_search_click_api_v1_search_click_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/config": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_config_api_v1_search_config_get"];
 put: operations["update_config_api_v1_search_config_put"];
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/config/reset": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["reset_config_api_v1_search_config_reset_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/search/health": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["search_health_api_v1_search_health_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/catalog": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_catalog_services_api_v1_services_catalog_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/catalog/all-with-instructors": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_all_services_with_instructors_api_v1_services_catalog_all_with_instructors_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/catalog/kids-available": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_kids_available_services_api_v1_services_catalog_kids_available_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/catalog/top-per-category": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_top_services_per_category_api_v1_services_catalog_top_per_category_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/categories": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_service_categories_api_v1_services_categories_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/instructor/add": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["add_service_to_profile_api_v1_services_instructor_add_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/services/search": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["search_services_api_v1_services_search_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/students/badges": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_student_badges_api_v1_students_badges_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/students/badges/earned": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_earned_student_badges_api_v1_students_badges_earned_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/students/badges/progress": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["list_in_progress_student_badges_api_v1_students_badges_progress_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/uploads/r2/finalize/profile-picture": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["finalize_profile_picture_api_v1_uploads_r2_finalize_profile_picture_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/uploads/r2/proxy": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["proxy_upload_to_r2_api_v1_uploads_r2_proxy_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/uploads/r2/signed-url": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["create_signed_upload_api_v1_uploads_r2_signed_url_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/users/me/profile-picture": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["upload_finalize_profile_picture_api_v1_users_me_profile_picture_post"];
 delete: operations["delete_profile_picture_api_v1_users_me_profile_picture_delete"];
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/users/profile-picture-urls": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_profile_picture_urls_batch_api_v1_users_profile_picture_urls_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/users/{user_id}/profile-picture-url": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get: operations["get_profile_picture_url_api_v1_users__user_id__profile_picture_url_get"];
 put?: never;
 post?: never;
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
 "/api/v1/webhooks/checkr": {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 get?: never;
 put?: never;
 post: operations["handle_checkr_webhook_api_v1_webhooks_checkr_post"];
 delete?: never;
 options?: never;
 head?: never;
 patch?: never;
 trace?: never;
 };
};
export type webhooks = Record<string, never>;
export type components = {
 schemas: {
 AccessGrantResponse: {
 access_id: string;
 invited_by_code?: string | null;
 phase: string;
 role: string;
 user_id: string;
 };
 AccountStatusChangeResponse: {
 message: string;
 new_status: string;
 previous_status: string;
 success: boolean;
 };
 AccountStatusResponse: {
 account_status: string;
 can_deactivate?: boolean | null;
 can_login: boolean;
 can_reactivate?: boolean | null;
 can_receive_bookings: boolean;
 can_suspend?: boolean | null;
 future_bookings_count?: number | null;
 has_future_bookings?: boolean | null;
 is_active: boolean;
 is_deactivated: boolean;
 is_suspended: boolean;
 role: string;
 user_id: string;
 };
 AddressCreate: {
 administrative_area: string;
 country_code: string;
 custom_label?: string | null;
 is_default: boolean;
 label?: string | null;
 latitude?: number | null;
 locality: string;
 longitude?: number | null;
 place_id?: string | null;
 postal_code: string;
 recipient_name?: string | null;
 street_line1: string;
 street_line2?: string | null;
 verification_status: string | null;
 };
 AddressListResponse: {
 items: components["schemas"]["AddressResponse"][];
 total: number;
 };
 AddressResponse: {
 administrative_area: string;
 country_code: string;
 custom_label?: string | null;
 district?: string | null;
 id: string;
 is_active: boolean;
 is_default: boolean;
 label?: string | null;
 latitude?: number | null;
 locality: string;
 location_metadata?: {
 [key: string]: unknown;
 } | null;
 longitude?: number | null;
 neighborhood?: string | null;
 place_id?: string | null;
 postal_code: string;
 recipient_name?: string | null;
 street_line1: string;
 street_line2?: string | null;
 subneighborhood?: string | null;
 verification_status: string | null;
 };
 AddressUpdate: {
 administrative_area?: string | null;
 country_code?: string | null;
 custom_label?: string | null;
 is_default?: boolean | null;
 label?: string | null;
 latitude?: number | null;
 locality?: string | null;
 longitude?: number | null;
 place_id?: string | null;
 postal_code?: string | null;
 recipient_name?: string | null;
 street_line1?: string | null;
 street_line2?: string | null;
 verification_status?: string | null;
 };
 AdminAuditActor: {
 email: string;
 id: string;
 };
 AdminAuditEntry: {
 action: string;
 admin: components["schemas"]["AdminAuditActor"];
 details?: {
 [key: string]: unknown;
 } | null;
 id: string;
 resource_id: string;
 resource_type: string;
 timestamp: string;
 };
 AdminAuditLogResponse: {
 entries: components["schemas"]["AdminAuditEntry"][];
 page: number;
 per_page: number;
 summary: components["schemas"]["AdminAuditLogSummary"];
 total: number;
 total_pages: number;
 };
 AdminAuditLogSummary: {
 captures_count: number;
 captures_total: number;
 refunds_count: number;
 refunds_total: number;
 };
 AdminAwardBadgeSchema: {
 criteria_type?: string | null;
 name: string;
 slug: string;
 };
 AdminAwardListResponse: {
 items: components["schemas"]["AdminAwardSchema"][];
 next_offset?: number | null;
 total: number;
 };
 AdminAwardSchema: {
 award_id: string;
 awarded_at: string;
 badge: components["schemas"]["AdminAwardBadgeSchema"];
 confirmed_at?: string | null;
 hold_until?: string | null;
 progress_snapshot?: {
 [key: string]: unknown;
 } | null;
 revoked_at?: string | null;
 status: string;
 student: components["schemas"]["AdminAwardStudentSchema"];
 };
 AdminAwardStudentSchema: {
 display_name?: string | null;
 email?: string | null;
 id: string;
 };
 AdminBookingDetailResponse: {
 booking_date: string;
 booking_end_utc?: string | null;
 booking_start_utc?: string | null;
 created_at?: string | null;
 end_time: string;
 id: string;
 instructor: components["schemas"]["AdminBookingPerson"];
 instructor_note?: string | null;
 instructor_timezone?: string | null;
 lesson_timezone?: string | null;
 location_type?: string | null;
 meeting_location?: string | null;
 payment: components["schemas"]["AdminBookingPaymentInfo"];
 service: components["schemas"]["AdminBookingServiceInfo"];
 start_time: string;
 status: string;
 student: components["schemas"]["AdminBookingPerson"];
 student_note?: string | null;
 student_timezone?: string | null;
 timeline: components["schemas"]["AdminBookingTimelineEvent"][];
 updated_at?: string | null;
 };
 AdminBookingListItem: {
 booking_date: string;
 booking_end_utc?: string | null;
 booking_start_utc?: string | null;
 created_at?: string | null;
 end_time: string;
 id: string;
 instructor: components["schemas"]["AdminBookingPerson"];
 instructor_timezone?: string | null;
 lesson_timezone?: string | null;
 payment_intent_id?: string | null;
 payment_status?: string | null;
 service_name: string;
 start_time: string;
 status: string;
 student: components["schemas"]["AdminBookingPerson"];
 student_timezone?: string | null;
 total_price: number;
 };
 AdminBookingListResponse: {
 bookings: components["schemas"]["AdminBookingListItem"][];
 page: number;
 per_page: number;
 total: number;
 total_pages: number;
 };
 AdminBookingPaymentInfo: {
 credits_applied: number;
 instructor_payout: number;
 lesson_price: number;
 payment_intent_id?: string | null;
 payment_status?: string | null;
 platform_fee: number;
 platform_revenue: number;
 stripe_url?: string | null;
 total_price: number;
 };
 AdminBookingPerson: {
 email: string;
 id: string;
 name: string;
 phone?: string | null;
 };
 AdminBookingServiceInfo: {
 duration_minutes: number;
 hourly_rate: number;
 id?: string | null;
 name: string;
 };
 AdminBookingStatsNeedsAction: {
 disputed: number;
 pending_completion: number;
 };
 AdminBookingStatsResponse: {
 needs_action: components["schemas"]["AdminBookingStatsNeedsAction"];
 this_week: components["schemas"]["AdminBookingStatsWeek"];
 today: components["schemas"]["AdminBookingStatsToday"];
 };
 AdminBookingStatsToday: {
 booking_count: number;
 revenue: number;
 };
 AdminBookingStatsWeek: {
 gmv: number;
 platform_revenue: number;
 };
 AdminBookingStatusUpdate: "COMPLETED" | "NO_SHOW";
 AdminBookingStatusUpdateRequest: {
 note?: string | null;
 status: components["schemas"]["AdminBookingStatusUpdate"];
 };
 AdminBookingStatusUpdateResponse: {
 booking_id: string;
 booking_status: string;
 success: boolean;
 };
 AdminBookingTimelineEvent: {
 amount?: number | null;
 event: string;
 timestamp: string;
 };
 AdminCancelBookingRequest: {
 note?: string | null;
 reason: string;
 refund: boolean;
 };
 AdminCancelBookingResponse: {
 booking_id: string;
 booking_status: string;
 refund_id?: string | null;
 refund_issued: boolean;
 success: boolean;
 };
 AdminInstructorDetailResponse: {
 bgc_completed_at?: string | null;
 bgc_dispute_note?: string | null;
 bgc_dispute_opened_at?: string | null;
 bgc_dispute_resolved_at?: string | null;
 bgc_expires_in_days?: number | null;
 bgc_in_dispute: boolean;
 bgc_includes_canceled: boolean;
 bgc_is_expired: boolean;
 bgc_report_id?: string | null;
 bgc_status?: string | null;
 bgc_valid_until?: string | null;
 consent_recent_at?: string | null;
 created_at?: string | null;
 email: string;
 id: string;
 is_live: boolean;
 name: string;
 updated_at?: string | null;
 };
 AdminNoShowResolution: "confirmed_after_review" | "dispute_upheld" | "cancelled";
 AdminNoShowResolutionRequest: {
 admin_notes?: string | null;
 resolution: components["schemas"]["AdminNoShowResolution"];
 };
 AdminNoShowResolutionResponse: {
 booking_id: string;
 resolution: string;
 settlement_outcome?: string | null;
 success: boolean;
 };
 AdminReferralsConfigOut: {
 expiry_months: number;
 flags: {
 [key: string]: boolean;
 };
 global_cap: number;
 hold_days: number;
 instructor_amount_cents: number;
 min_basket_cents: number;
 source: "db" | "defaults";
 student_amount_cents: number;
 version: number | null;
 };
 AdminReferralsHealthOut: {
 backlog_pending_due: number;
 last_run_age_s?: number | null;
 pending_total: number;
 unlocked_total: number;
 void_total: number;
 workers: string[];
 workers_alive: number;
 };
 AdminReferralsSummaryOut: {
 attributions_24h: number;
 cap_utilization_percent: number;
 clicks_24h: number;
 counts_by_status: {
 [key: string]: number;
 };
 top_referrers: components["schemas"]["TopReferrerOut"][];
 };
 AdminRefundReason: "instructor_no_show" | "dispute" | "platform_error" | "other";
 AdminRefundRequest: {
 amount_cents?: number | null;
 note?: string | null;
 reason: components["schemas"]["AdminRefundReason"];
 };
 AdminRefundResponse: {
 amount_refunded_cents: number;
 booking_id: string;
 booking_status: string;
 message: string;
 refund_id: string;
 success: boolean;
 };
 AdminSearchConfigResponse: {
 available_embedding_models: components["schemas"]["ModelOption"][];
 available_parsing_models: components["schemas"]["ModelOption"][];
 current_in_flight_requests: number;
 embedding_model: string;
 embedding_timeout_ms: number;
 high_load_budget_ms: number;
 high_load_threshold: number;
 location_model: string;
 location_timeout_ms: number;
 openai_max_retries: number;
 parsing_model: string;
 parsing_timeout_ms: number;
 search_budget_ms: number;
 uncached_concurrency: number;
 };
 AdminSearchConfigUpdate: {
 embedding_timeout_ms?: number | null;
 high_load_budget_ms?: number | null;
 high_load_threshold?: number | null;
 location_model?: string | null;
 location_timeout_ms?: number | null;
 openai_max_retries?: number | null;
 parsing_model?: string | null;
 parsing_timeout_ms?: number | null;
 search_budget_ms?: number | null;
 uncached_concurrency?: number | null;
 };
 AlertAcknowledgeResponse: {
 alert_type: string;
 status: string;
 };
 AlertDetail: {
 created_at: string;
 details?: {
 [key: string]: unknown;
 } | null;
 email_sent: boolean;
 github_issue: boolean;
 id: string;
 message: string;
 severity: string;
 title: string;
 type: string;
 };
 AlertInfo: {
 message: string;
 severity: string;
 timestamp: string;
 type: string;
 };
 AlertSummaryResponse: {
 by_day: components["schemas"]["DailyAlertCount"][];
 by_severity: {
 [key: string]: number;
 };
 by_type: {
 [key: string]: number;
 };
 days: number;
 total: number;
 };
 AllServicesMetadata: {
 cached_for_seconds: number;
 total_categories: number;
 total_services?: number | null;
 updated_at: string;
 };
 AllServicesWithInstructorsResponse: {
 categories?: components["schemas"]["CategoryWithServices"][];
 metadata: components["schemas"]["AllServicesMetadata"];
 };
 AppendHistoryResponse: {
 count: number;
 status: string;
 };
 ApplyToDateRangeRequest: {
 end_date: string;
 from_week_start: string;
 start_date: string;
 };
 ApplyToDateRangeResponse: {
 dates_processed: number;
 dates_with_slots: number;
 dates_with_windows: number;
 days_written: number;
 edited_dates?: string[];
 end_date: string;
 message: string;
 skipped_past_targets: number;
 start_date: string;
 weeks_affected: number;
 weeks_applied: number;
 windows_created: number;
 written_dates?: string[];
 };
 AuditLogListResponse: {
 items: components["schemas"]["AuditLogView"][];
 limit: number;
 offset: number;
 total: number;
 };
 AuditLogView: {
 action: string;
 actor_id?: string | null;
 actor_role?: string | null;
 after?: {
 [key: string]: unknown;
 } | null;
 before?: {
 [key: string]: unknown;
 } | null;
 entity_id: string;
 entity_type: string;
 id: string;
 occurred_at: string;
 };
 AuthUserResponse: {
 email: string;
 first_name: string;
 founding_instructor_granted?: boolean | null;
 has_profile_picture: boolean | null;
 id: string;
 is_active: boolean;
 last_name: string;
 permissions?: string[];
 phone?: string | null;
 phone_verified: boolean | null;
 profile_picture_version: number | null;
 roles?: string[];
 timezone?: string | null;
 zip_code?: string | null;
 };
 AuthUserWithPermissionsResponse: {
 beta_access?: boolean | null;
 beta_invited_by?: string | null;
 beta_phase?: string | null;
 beta_role?: string | null;
 email: string;
 first_name: string;
 founding_instructor_granted?: boolean | null;
 has_profile_picture: boolean | null;
 id: string;
 is_active: boolean;
 last_name: string;
 permissions?: string[];
 phone?: string | null;
 phone_verified: boolean | null;
 profile_picture_version: number | null;
 roles?: string[];
 timezone?: string | null;
 zip_code?: string | null;
 };
 AutocompleteResponse: {
 items: components["schemas"]["PlaceSuggestion"][];
 total: number;
 };
 AvailabilityCacheMetricsResponse: {
 availability_cache_metrics: {
 [key: string]: unknown;
 };
 cache_tiers_info: {
 [key: string]: string;
 };
 recommendations: string[];
 top_cached_keys_sample: string[];
 };
 AvailabilityCheckRequest: {
 booking_date: string;
 end_time: string;
 instructor_id: string;
 instructor_service_id: string;
 start_time: string;
 };
 AvailabilityCheckResponse: {
 available: boolean;
 conflicts_with?: {
 [key: string]: unknown;
 }[] | null;
 min_advance_hours?: number | null;
 reason?: string | null;
 time_info?: {
 [key: string]: unknown;
 } | null;
 };
 AvailabilityWindowResponse: {
 end_time: string;
 id: string;
 instructor_id: string;
 specific_date: string;
 start_time: string;
 };
 AvailabilityWindowUpdate: {
 end_time?: string | null;
 start_time?: string | null;
 };
 BGCCaseCountsResponse: {
 pending: number;
 review: number;
 };
 BGCCaseItemModel: {
 bgc_completed_at?: string | null;
 bgc_eta?: string | null;
 bgc_expires_in_days?: number | null;
 bgc_includes_canceled: boolean;
 bgc_is_expired: boolean;
 bgc_report_id?: string | null;
 bgc_status?: string | null;
 bgc_valid_until?: string | null;
 checkr_report_url?: string | null;
 consent_recent: boolean;
 consent_recent_at?: string | null;
 created_at?: string | null;
 dispute_note?: string | null;
 dispute_opened_at?: string | null;
 dispute_resolved_at?: string | null;
 email: string;
 in_dispute: boolean;
 instructor_id: string;
 is_live: boolean;
 name: string;
 updated_at?: string | null;
 };
 BGCCaseListResponse: {
 has_next: boolean;
 has_prev: boolean;
 items: components["schemas"]["BGCCaseItemModel"][];
 page: number;
 page_size: number;
 total: number;
 total_pages: number;
 };
 BGCDisputeResponse: {
 dispute_note?: string | null;
 dispute_opened_at?: string | null;
 dispute_resolved_at?: string | null;
 in_dispute: boolean;
 ok: boolean;
 resumed: boolean;
 scheduled_for?: string | null;
 };
 BGCExpiringItem: {
 bgc_valid_until?: string | null;
 email?: string | null;
 instructor_id: string;
 };
 BGCHistoryItem: {
 completed_at: string;
 created_at: string;
 env: string;
 id: string;
 package?: string | null;
 report_id_present: boolean;
 result: string;
 };
 BGCHistoryResponse: {
 items: components["schemas"]["BGCHistoryItem"][];
 next_cursor?: string | null;
 };
 BGCLatestConsentResponse: {
 consent_version: string;
 consented_at: string;
 instructor_id: string;
 ip_address?: string | null;
 };
 BGCOverrideResponse: {
 new_status: "passed" | "failed";
 ok: boolean;
 };
 BGCReviewCountResponse: {
 count: number;
 };
 BGCReviewItemModel: {
 bgc_completed_at?: string | null;
 bgc_eta?: string | null;
 bgc_expires_in_days?: number | null;
 bgc_includes_canceled: boolean;
 bgc_is_expired: boolean;
 bgc_report_id?: string | null;
 bgc_status?: string | null;
 bgc_valid_until?: string | null;
 checkr_report_url?: string | null;
 consented_at_recent: boolean;
 consented_at_recent_at?: string | null;
 created_at?: string | null;
 dispute_note?: string | null;
 dispute_opened_at?: string | null;
 dispute_resolved_at?: string | null;
 email: string;
 in_dispute: boolean;
 instructor_id: string;
 is_live: boolean;
 name: string;
 updated_at?: string | null;
 };
 BGCReviewListResponse: {
 items: components["schemas"]["BGCReviewItemModel"][];
 next_cursor?: string | null;
 };
 BGCWebhookLogEntry: {
 candidate_id?: string | null;
 created_at: string;
 delivery_id?: string | null;
 event_type: string;
 http_status?: number | null;
 id: string;
 instructor_id?: string | null;
 invitation_id?: string | null;
 payload: {
 [key: string]: unknown;
 };
 report_id?: string | null;
 resource_id?: string | null;
 result?: string | null;
 signature?: string | null;
 };
 BGCWebhookLogListResponse: {
 error_count_24h: number;
 items: components["schemas"]["BGCWebhookLogEntry"][];
 next_cursor?: string | null;
 };
 BGCWebhookStatsResponse: {
 error_count_24h: number;
 };
 BackgroundCheckInviteRequest: {
 package_slug?: string | null;
 };
 BackgroundCheckInviteResponse: {
 already_in_progress: boolean;
 candidate_id?: string | null;
 invitation_id?: string | null;
 ok: boolean;
 report_id?: string | null;
 status: "pending" | "review" | "consider" | "passed" | "failed" | "canceled";
 };
 BackgroundCheckStatusResponse: {
 bgc_includes_canceled: boolean;
 completed_at?: string | null;
 consent_recent: boolean;
 consent_recent_at?: string | null;
 env: "sandbox" | "production";
 eta?: string | null;
 expires_in_days?: number | null;
 is_expired: boolean;
 report_id?: string | null;
 status: "pending" | "review" | "consider" | "passed" | "failed" | "canceled";
 valid_until?: string | null;
 };
 BackupCodesResponse: {
 backup_codes: string[];
 };
 BadgeProgressView: {
 current?: number | null;
 goal?: number | null;
 percent?: number | null;
 } & {
 [key: string]: unknown;
 };
 BetaMetricsSummaryResponse: {
 invites_errors_24h: number;
 invites_sent_24h: number;
 phase_counts_24h: {
 [key: string]: number;
 };
 };
 BetaSettingsResponse: {
 allow_signup_without_invite: boolean;
 beta_disabled: boolean;
 beta_phase: string;
 };
 BetaSettingsUpdateRequest: {
 allow_signup_without_invite: boolean;
 beta_disabled: boolean;
 beta_phase: string;
 };
 BlackoutDateCreate: {
 date: string;
 reason?: string | null;
 };
 BlackoutDateResponse: {
 created_at: string;
 date: string;
 id: string;
 instructor_id: string;
 reason?: string | null;
 };
 Body_dispute_completion_api_v1_instructor_bookings__booking_id__dispute_post: {
 reason: string;
 };
 Body_login_api_v1_auth_login_post: {
 client_id?: string | null;
 client_secret?: string | null;
 grant_type?: string | null;
 password: string;
 scope: string;
 username: string;
 };
 Body_proxy_upload_to_r2_api_v1_uploads_r2_proxy_post: {
 content_type: string;
 file: string;
 key: string;
 };
 Body_respond_to_review_api_v1_reviews__review_id__respond_post: {
 response_text: string;
 };
 BookedSlotsResponse: {
 booked_slots: {
 [key: string]: unknown;
 }[];
 week_end: string;
 week_start: string;
 };
 BookingCancel: {
 reason: string;
 };
 BookingConfirmPayment: {
 payment_method_id: string;
 save_payment_method: boolean;
 };
 BookingCreate: {
 booking_date: string;
 end_time?: string | null;
 instructor_id: string;
 instructor_service_id: string;
 location_type: ("student_home" | "instructor_location" | "neutral" | "remote" | "in_person") | null;
 meeting_location?: string | null;
 selected_duration: number;
 start_time: string;
 student_note?: string | null;
 timezone?: string | null;
 };
 BookingCreateResponse: {
 auth_attempted_at?: string | null;
 auth_failure_count?: number | null;
 auth_last_error?: string | null;
 auth_scheduled_for?: string | null;
 booking_date: string;
 booking_end_utc?: string | null;
 booking_start_utc?: string | null;
 cancellation_reason: string | null;
 cancelled_at: string | null;
 cancelled_by_id: string | null;
 completed_at: string | null;
 confirmed_at: string | null;
 created_at: string;
 credits_reserved_cents?: number | null;
 duration_minutes: number;
 end_time: string;
 has_locked_funds?: boolean | null;
 hourly_rate: number;
 id: string;
 instructor: components["schemas"]["InstructorInfo"];
 instructor_id: string;
 instructor_note: string | null;
 instructor_payout_amount?: number | null;
 instructor_service: components["schemas"]["ServiceInfo"];
 instructor_service_id: string;
 instructor_timezone?: string | null;
 lesson_timezone?: string | null;
 location_type: string | null;
 lock_resolution?: string | null;
 lock_resolved_at?: string | null;
 locked_amount_cents?: number | null;
 locked_at?: string | null;
 meeting_location: string | null;
 no_show_dispute_reason?: string | null;
 no_show_disputed?: boolean | null;
 no_show_disputed_at?: string | null;
 no_show_reported_at?: string | null;
 no_show_reported_by?: string | null;
 no_show_resolution?: string | null;
 no_show_resolved_at?: string | null;
 no_show_type?: string | null;
 payment_summary?: components["schemas"]["PaymentSummary"] | null;
 refunded_to_card_amount?: number | null;
 requires_payment_method: boolean;
 rescheduled_from?: components["schemas"]["RescheduledFromInfo"] | null;
 rescheduled_from_booking_id?: string | null;
 rescheduled_to_booking_id?: string | null;
 service_area: string | null;
 service_name: string;
 settlement_outcome?: string | null;
 setup_intent_client_secret?: string | null;
 start_time: string;
 status: components["schemas"]["BookingStatus"];
 student: components["schemas"]["StudentInfo"];
 student_credit_amount?: number | null;
 student_id: string;
 student_note: string | null;
 student_timezone?: string | null;
 total_price: number;
 };
 BookingPaymentMethodUpdate: {
 payment_method_id: string;
 set_as_default: boolean;
 };
 BookingPreviewResponse: {
 booking_date: string;
 booking_id: string;
 duration_minutes: number;
 end_time: string;
 instructor_first_name: string;
 instructor_last_name: string;
 location_type: string;
 location_type_display: string;
 meeting_location: string | null;
 service_area: string | null;
 service_name: string;
 start_time: string;
 status: string;
 student_first_name: string;
 student_last_name: string;
 student_note: string | null;
 total_price: number;
 };
 BookingRescheduleRequest: {
 booking_date: string;
 instructor_service_id?: string | null;
 selected_duration: number;
 start_time: string;
 };
 BookingResponse: {
 auth_attempted_at?: string | null;
 auth_failure_count?: number | null;
 auth_last_error?: string | null;
 auth_scheduled_for?: string | null;
 booking_date: string;
 booking_end_utc?: string | null;
 booking_start_utc?: string | null;
 cancellation_reason: string | null;
 cancelled_at: string | null;
 cancelled_by_id: string | null;
 completed_at: string | null;
 confirmed_at: string | null;
 created_at: string;
 credits_reserved_cents?: number | null;
 duration_minutes: number;
 end_time: string;
 has_locked_funds?: boolean | null;
 hourly_rate: number;
 id: string;
 instructor: components["schemas"]["InstructorInfo"];
 instructor_id: string;
 instructor_note: string | null;
 instructor_payout_amount?: number | null;
 instructor_service: components["schemas"]["ServiceInfo"];
 instructor_service_id: string;
 instructor_timezone?: string | null;
 lesson_timezone?: string | null;
 location_type: string | null;
 lock_resolution?: string | null;
 lock_resolved_at?: string | null;
 locked_amount_cents?: number | null;
 locked_at?: string | null;
 meeting_location: string | null;
 no_show_dispute_reason?: string | null;
 no_show_disputed?: boolean | null;
 no_show_disputed_at?: string | null;
 no_show_reported_at?: string | null;
 no_show_reported_by?: string | null;
 no_show_resolution?: string | null;
 no_show_resolved_at?: string | null;
 no_show_type?: string | null;
 payment_summary?: components["schemas"]["PaymentSummary"] | null;
 refunded_to_card_amount?: number | null;
 rescheduled_from?: components["schemas"]["RescheduledFromInfo"] | null;
 rescheduled_from_booking_id?: string | null;
 rescheduled_to_booking_id?: string | null;
 service_area: string | null;
 service_name: string;
 settlement_outcome?: string | null;
 start_time: string;
 status: components["schemas"]["BookingStatus"];
 student: components["schemas"]["StudentInfo"];
 student_credit_amount?: number | null;
 student_id: string;
 student_note: string | null;
 student_timezone?: string | null;
 total_price: number;
 };
 BookingStatsResponse: {
 average_rating?: number | null;
 cancelled_bookings: number;
 completed_bookings: number;
 this_month_earnings: number;
 total_bookings: number;
 total_earnings: number;
 upcoming_bookings: number;
 };
 BookingStatus: "PENDING" | "CONFIRMED" | "COMPLETED" | "CANCELLED" | "NO_SHOW";
 BookingSummary: {
 date: string;
 id: string;
 service_name: string;
 start_time: string;
 };
 BookingUpdate: {
 instructor_note?: string | null;
 meeting_location?: string | null;
 };
 BudgetInfo: {
 degradation_level: string;
 initial_ms: number;
 over_budget: boolean;
 remaining_ms: number;
 skipped_operations?: string[];
 };
 BulkUpdateResponse: {
 failed: number;
 results: components["schemas"]["OperationResult"][];
 skipped: number;
 successful: number;
 };
 CacheHealthStatus: {
 errors: number;
 hit_rate: string;
 recommendations: string[];
 status: string;
 total_requests: number;
 };
 CacheMetricsResponse: {
 availability_metrics: {
 [key: string]: unknown;
 };
 errors: number;
 hit_rate: string;
 hits: number;
 misses: number;
 performance_insights: string[];
 redis_info?: {
 [key: string]: unknown;
 } | null;
 };
 CandidateCategoryTrend: {
 category: string;
 count: number;
 date: string;
 };
 CandidateCategoryTrendsResponse: components["schemas"]["CandidateCategoryTrend"][];
 CandidateScoreDistributionResponse: {
 gte_0_70_lt_0_80: number;
 gte_0_80_lt_0_90: number;
 gte_0_90: number;
 lt_0_70: number;
 };
 CandidateServiceQueriesResponse: components["schemas"]["CandidateServiceQuery"][];
 CandidateServiceQuery: {
 position: number;
 results_count: number | null;
 score: number | null;
 search_query: string;
 searched_at: string;
 source: string | null;
 };
 CandidateSummaryResponse: {
 avg_candidates_per_event: number;
 events_with_candidates: number;
 source_breakdown: {
 [key: string]: number;
 };
 total_candidates: number;
 zero_result_events_with_candidates: number;
 };
 CandidateTopService: {
 active_instructors: number;
 avg_position: number;
 avg_score: number;
 candidate_count: number;
 category_name: string;
 opportunity_score: number;
 service_catalog_id: string;
 service_name: string;
 };
 CandidateTopServicesResponse: components["schemas"]["CandidateTopService"][];
 CatalogServiceMinimalResponse: {
 id: string;
 name: string;
 slug: string;
 };
 CatalogServiceResponse: {
 category?: string | null;
 category_id: string;
 description?: string | null;
 display_order?: number | null;
 id: string;
 max_recommended_price?: number | null;
 min_recommended_price?: number | null;
 name: string;
 online_capable?: boolean | null;
 requires_certification?: boolean | null;
 search_terms: string[];
 slug: string;
 typical_duration_options: number[];
 };
 CategoryResponse: {
 description?: string | null;
 display_order: number;
 icon_name?: string | null;
 id: string;
 name: string;
 slug: string;
 subtitle?: string | null;
 };
 CategoryServiceDetail: {
 active_instructors: number;
 actual_max_price?: number | null;
 actual_min_price?: number | null;
 category_id: string;
 demand_score: number;
 description?: string | null;
 display_order?: number | null;
 id: string;
 instructor_count: number;
 is_active?: boolean | null;
 is_trending: boolean;
 name: string;
 online_capable?: boolean | null;
 requires_certification?: boolean | null;
 search_terms?: string[];
 slug: string;
 };
 CategoryWithServices: {
 description?: string | null;
 icon_name?: string | null;
 id: string;
 name: string;
 services?: components["schemas"]["CategoryServiceDetail"][];
 slug: string;
 subtitle?: string | null;
 };
 CheckoutApplyRequest: {
 order_id: string;
 };
 CheckoutApplyResponse: {
 applied_cents: number;
 };
 CheckoutResponse: {
 amount: number;
 application_fee: number;
 client_secret?: string | null;
 payment_intent_id: string;
 requires_action: boolean;
 status: string;
 success: boolean;
 };
 CodebaseCategoryStats: {
 files: number;
 lines: number;
 };
 CodebaseFileInfo: {
 lines: number;
 lines_with_blanks: number;
 path: string;
 size_kb: number;
 };
 CodebaseHistoryEntry: {
 backend_lines: number;
 categories?: {
 [key: string]: {
 [key: string]: components["schemas"]["CodebaseCategoryStats"];
 };
 } | null;
 frontend_lines: number;
 git_commits: number;
 timestamp: string;
 total_files: number;
 total_lines: number;
 };
 CodebaseHistoryResponse: {
 current?: components["schemas"]["CodebaseMetricsResponse"] | null;
 items?: components["schemas"]["CodebaseHistoryEntry"][];
 };
 CodebaseMetricsResponse: {
 backend: components["schemas"]["CodebaseSection"];
 frontend: components["schemas"]["CodebaseSection"];
 git: components["schemas"]["GitStats"];
 summary: components["schemas"]["CodebaseMetricsSummary"];
 timestamp: string;
 };
 CodebaseMetricsSummary: {
 total_files: number;
 total_lines: number;
 };
 CodebaseSection: {
 categories?: {
 [key: string]: components["schemas"]["CodebaseCategoryStats"];
 };
 largest_files?: components["schemas"]["CodebaseFileInfo"][];
 total_files: number;
 total_lines: number;
 total_lines_with_blanks: number;
 };
 ConsentPayload: {
 consent_version: string;
 disclosure_version: string;
 user_agent?: string | null;
 };
 ConsentResponse: {
 ok: boolean;
 };
 ConversationDetail: {
 created_at: string;
 id: string;
 next_booking?: components["schemas"]["BookingSummary"] | null;
 other_user: components["schemas"]["UserSummary"];
 state: string;
 upcoming_bookings?: components["schemas"]["BookingSummary"][];
 };
 ConversationListItem: {
 id: string;
 last_message?: components["schemas"]["LastMessage"] | null;
 next_booking?: components["schemas"]["BookingSummary"] | null;
 other_user: components["schemas"]["UserSummary"];
 state: string;
 unread_count: number;
 upcoming_booking_count: number;
 upcoming_bookings?: components["schemas"]["BookingSummary"][];
 };
 ConversationListResponse: {
 conversations: components["schemas"]["ConversationListItem"][];
 next_cursor?: string | null;
 };
 ConversionBehavior: {
 avg_days_to_conversion: number;
 avg_searches_before_conversion: number;
 most_common_first_search: string;
 };
 ConversionMetricsResponse: {
 conversion_behavior: components["schemas"]["ConversionBehavior"];
 guest_engagement: components["schemas"]["GuestEngagement"];
 guest_sessions: components["schemas"]["GuestConversionMetrics"];
 period: components["schemas"]["DateRange"];
 };
 CopyWeekRequest: {
 from_week_start: string;
 to_week_start: string;
 };
 CopyWeekResponse: {
 message: string;
 source_week_start: string;
 target_week_start: string;
 windows_copied: number;
 };
 CoverageFeatureCollectionResponse: {
 features: {
 [key: string]: unknown;
 }[];
 type: string;
 };
 CreateCheckoutRequest: {
 booking_id: string;
 payment_method_id?: string | null;
 requested_credit_cents?: number | null;
 save_payment_method: boolean;
 };
 CreateConversationRequest: {
 initial_message?: string | null;
 instructor_id: string;
 };
 CreateConversationResponse: {
 created: boolean;
 id: string;
 };
 CreateSignedUploadRequest: {
 content_type: string;
 filename: string;
 purpose: "background_check" | "profile_picture";
 size_bytes: number;
 };
 CreditBalanceResponse: {
 available: number;
 expires_at?: string | null;
 pending: number;
 };
 DailyAlertCount: {
 count: number;
 date: string;
 };
 DailySearchTrend: {
 date: string;
 total_searches: number;
 unique_guests: number;
 unique_users: number;
 };
 DashboardLinkResponse: {
 dashboard_url: string;
 expires_in_minutes: number;
 };
 DataExportResponse: {
 data: {
 [key: string]: unknown;
 };
 message: string;
 status: string;
 };
 DatabaseHealthResponse: {
 error?: string | null;
 message: string;
 pool_status?: {
 [key: string]: unknown;
 } | null;
 status: string;
 };
 DatabasePoolStatusResponse: {
 configuration: {
 [key: string]: unknown;
 };
 pool: {
 [key: string]: unknown;
 };
 recommendations: {
 [key: string]: unknown;
 };
 status: string;
 };
 DatabaseStatsResponse: {
 configuration: {
 [key: string]: unknown;
 };
 health: {
 [key: string]: unknown;
 };
 pool: {
 [key: string]: unknown;
 };
 status: string;
 };
 DateRange: {
 days: number;
 end: string;
 start: string;
 };
 DeleteBlackoutResponse: {
 blackout_id: string;
 message: string;
 };
 DeleteMessageResponse: {
 message: string;
 success: boolean;
 };
 DeleteWindowResponse: {
 message: string;
 window_id: string;
 };
 EarningsExportRequest: {
 end_date?: string | null;
 format: "csv" | "pdf";
 start_date?: string | null;
 };
 EarningsResponse: {
 average_earning?: number | null;
 booking_count?: number | null;
 hours_invoiced?: number | null;
 invoices?: components["schemas"]["InstructorInvoiceSummary"][];
 period_end?: string | null;
 period_start?: string | null;
 service_count?: number | null;
 total_earned?: number | null;
 total_fees?: number | null;
 total_lesson_value?: number | null;
 total_platform_fees?: number | null;
 total_tips?: number | null;
 };
 EditMessageRequest: {
 content: string;
 };
 ExistingReviewIdsResponse: string[];
 ExportAnalyticsResponse: {
 download_url?: string | null;
 format: string;
 message: string;
 status: string;
 user: string;
 };
 ExtendedCacheStats: {
 basic_stats: {
 [key: string]: unknown;
 };
 key_patterns?: {
 [key: string]: number;
 } | null;
 redis_info?: {
 [key: string]: unknown;
 } | null;
 };
 FavoriteResponse: {
 already_favorited?: boolean | null;
 favorite_id?: string | null;
 message: string;
 not_favorited?: boolean | null;
 success: boolean;
 };
 FavoriteStatusResponse: {
 is_favorited: boolean;
 };
 FavoritedInstructor: {
 email: string;
 favorited_at?: string | null;
 first_name: string;
 id: string;
 is_active: boolean;
 last_name: string;
 profile?: components["schemas"]["InstructorProfileResponse"] | null;
 };
 FavoritesList: {
 favorites: components["schemas"]["FavoritedInstructor"][];
 total: number;
 };
 FinalizeProfilePicturePayload: {
 object_key: string;
 };
 FinalizeProfilePictureRequest: {
 object_key: string;
 };
 FoundingCountResponse: {
 cap: number;
 count: number;
 remaining: number;
 };
 GatedPingResponse: {
 ok: boolean;
 };
 GitStats: {
 current_branch: string;
 first_commit: string;
 last_commit: string;
 total_commits: number;
 unique_contributors: number;
 };
 GuestConversionMetrics: {
 conversion_rate: number;
 converted: number;
 total: number;
 };
 GuestEngagement: {
 avg_searches_per_session: number;
 engaged_sessions: number;
 engagement_rate: number;
 };
 GuestSearchHistoryCreate: {
 guest_session_id: string;
 results_count?: number | null;
 search_query: string;
 search_type: string;
 };
 GuestSessionResponse: {
 guest_id: string;
 };
 HTTPValidationError: {
 detail?: components["schemas"]["ValidationError"][];
 };
 HealthCheckResponse: {
 checks: {
 [key: string]: boolean;
 };
 service: string;
 status: string;
 timestamp?: string;
 version: string;
 };
 HealthLiteResponse: {
 status: string;
 };
 HealthResponse: {
 environment: string;
 service: string;
 status: string;
 timestamp: string;
 version: string;
 };
 IdentityRefreshResponse: {
 status: string;
 verified: boolean;
 };
 IdentitySessionResponse: {
 client_secret: string;
 verification_session_id: string;
 };
 InstantPayoutResponse: {
 ok: boolean;
 payout_id?: string | null;
 status?: string | null;
 };
 InstructorInfo: {
 first_name: string;
 id: string;
 last_initial: string;
 };
 InstructorInvoiceSummary: {
 booking_id: string;
 created_at: string;
 duration_minutes?: number | null;
 instructor_share_cents: number;
 lesson_date: string;
 lesson_price_cents: number;
 platform_fee_cents: number;
 platform_fee_rate: number;
 service_name?: string | null;
 start_time?: string | null;
 status: string;
 student_fee_cents: number;
 student_name?: string | null;
 tip_cents: number;
 total_paid_cents: number;
 };
 InstructorProfileCreate: {
 bio: string;
 buffer_time_minutes: number;
 min_advance_booking_hours: number;
 services: components["schemas"]["ServiceCreate"][];
 years_experience: number;
 };
 InstructorProfileResponse: {
 background_check_object_key?: string | null;
 background_check_uploaded_at?: string | null;
 bio: string;
 buffer_time_minutes: number;
 created_at: string;
 favorited_count: number;
 id: string;
 identity_verification_session_id?: string | null;
 identity_verified_at?: string | null;
 is_favorited?: boolean | null;
 is_founding_instructor: boolean;
 is_live: boolean;
 min_advance_booking_hours: number;
 onboarding_completed_at?: string | null;
 preferred_public_spaces?: components["schemas"]["PreferredPublicSpaceOut"][];
 preferred_teaching_locations?: components["schemas"]["PreferredTeachingLocationOut"][];
 service_area_boroughs?: string[];
 service_area_neighborhoods?: components["schemas"]["ServiceAreaNeighborhood"][];
 service_area_summary?: string | null;
 services: components["schemas"]["ServiceResponse"][];
 skills_configured: boolean;
 updated_at?: string | null;
 user: components["schemas"]["UserBasicPrivacy"];
 user_id: string;
 years_experience: number;
 };
 InstructorProfileUpdate: {
 bio?: string | null;
 buffer_time_minutes?: number | null;
 min_advance_booking_hours?: number | null;
 preferred_public_spaces?: components["schemas"]["PreferredPublicSpaceIn"][] | null;
 preferred_teaching_locations?: components["schemas"]["PreferredTeachingLocationIn"][] | null;
 services?: components["schemas"]["ServiceCreate"][] | null;
 years_experience?: number | null;
 };
 InstructorRatingsResponse: {
 by_service?: {
 [key: string]: unknown;
 }[];
 confidence_level: string;
 overall: {
 [key: string]: unknown;
 };
 };
 InstructorServiceCreate: {
 catalog_service_id: string;
 custom_description?: string | null;
 duration_options?: number[] | null;
 hourly_rate: number;
 };
 InstructorServiceResponse: {
 catalog_service_id: string;
 category: string;
 created_at?: string | null;
 description?: string | null;
 duration_options: number[];
 hourly_rate: number;
 id: string;
 is_active: boolean;
 name: string;
 updated_at?: string | null;
 };
 InstructorSummary: {
 bio_snippet?: string | null;
 first_name: string;
 id: string;
 is_founding_instructor: boolean;
 last_initial: string;
 profile_picture_url?: string | null;
 verified: boolean;
 years_experience?: number | null;
 };
 InviteBatchAsyncStartResponse: {
 task_id: string;
 };
 InviteBatchProgressResponse: {
 current: number;
 failed: number;
 failed_items?: components["schemas"]["InviteBatchSendFailure"][] | null;
 sent: number;
 sent_items?: components["schemas"]["InviteSendResponse"][] | null;
 state: string;
 task_id: string;
 total: number;
 };
 InviteBatchSendFailure: {
 email: string;
 reason: string;
 };
 InviteBatchSendRequest: {
 base_url?: string | null;
 emails?: string[];
 expires_in_days: number;
 role: string;
 source?: string | null;
 };
 InviteBatchSendResponse: {
 failed: components["schemas"]["InviteBatchSendFailure"][];
 sent: components["schemas"]["InviteSendResponse"][];
 };
 InviteConsumeRequest: {
 code: string;
 phase: string;
 role: string;
 user_id: string;
 };
 InviteGenerateRequest: {
 count: number;
 emails?: string[] | null;
 expires_in_days: number;
 role: string;
 source?: string | null;
 };
 InviteGenerateResponse: {
 invites: components["schemas"]["InviteRecord"][];
 };
 InviteRecord: {
 code: string;
 email?: string | null;
 expires_at: string;
 id: string;
 role: string;
 };
 InviteSendRequest: {
 base_url?: string | null;
 expires_in_days: number;
 grant_founding_status: boolean;
 role: string;
 source?: string | null;
 to_email: string;
 };
 InviteSendResponse: {
 code: string;
 email: string;
 id: string;
 join_url: string;
 welcome_url: string;
 };
 InviteValidateResponse: {
 code?: string | null;
 email?: string | null;
 expires_at?: string | null;
 reason?: string | null;
 role?: string | null;
 used_at?: string | null;
 valid: boolean;
 };
 LastMessage: {
 content: string;
 created_at: string;
 is_from_me: boolean;
 };
 LineItem: {
 amount_cents: number;
 label: string;
 };
 LiveAlertItem: {
 message: string;
 severity: string;
 time: string;
 type: string;
 };
 LiveAlertsResponse: {
 alerts: components["schemas"]["LiveAlertItem"][];
 count: number;
 minutes: number;
 };
 LocationResolutionInfo: {
 query: string;
 resolved_name?: string | null;
 resolved_regions?: string[] | null;
 successful_tier?: number | null;
 tiers?: components["schemas"]["LocationTierResult"][];
 };
 LocationTierResult: {
 attempted: boolean;
 confidence?: number | null;
 details?: string | null;
 duration_ms: number;
 result?: string | null;
 status: components["schemas"]["StageStatus"];
 tier: number;
 };
 LoginResponse: {
 access_token?: string | null;
 requires_2fa: boolean;
 temp_token?: string | null;
 token_type?: string | null;
 };
 MarkMessagesReadRequest: {
 conversation_id?: string | null;
 message_ids?: string[] | null;
 };
 MarkMessagesReadResponse: {
 messages_marked: number;
 success: boolean;
 };
 MemoryMetrics: {
 percent: number;
 total_mb: number;
 used_mb: number;
 };
 MessageConfigResponse: {
 edit_window_minutes: number;
 };
 MessageResponse: {
 booking_details?: components["schemas"]["BookingSummary"] | null;
 booking_id?: string | null;
 content: string;
 conversation_id: string;
 created_at: string;
 delivered_at?: string | null;
 edited_at?: string | null;
 id: string;
 is_deleted: boolean;
 is_from_me: boolean;
 message_type: string;
 reactions?: components["schemas"]["ReactionInfo"][];
 read_by?: components["schemas"]["ReadReceiptEntry"][];
 sender_id?: string | null;
 };
 MessagesResponse: {
 has_more: boolean;
 messages: components["schemas"]["MessageResponse"][];
 next_cursor?: string | null;
 };
 MockStatusResponse: {
 ok: boolean;
 status: "pending" | "review" | "consider" | "passed" | "failed" | "canceled";
 };
 ModelOption: {
 description: string;
 id: string;
 name: string;
 };
 MonitoringDashboardResponse: {
 alerts: components["schemas"]["AlertInfo"][];
 cache: components["schemas"]["CacheHealthStatus"];
 database: {
 [key: string]: unknown;
 };
 memory: components["schemas"]["MemoryMetrics"];
 recommendations: components["schemas"]["PerformanceRecommendation"][];
 requests: components["schemas"]["RequestMetrics"];
 status: string;
 timestamp: string;
 };
 NLSearchMeta: {
 cache_hit: boolean;
 corrected_query?: string | null;
 degradation_reasons?: string[];
 degraded: boolean;
 diagnostics?: components["schemas"]["SearchDiagnostics"] | null;
 filter_stats?: {
 [key: string]: number;
 } | null;
 filters_applied?: string[];
 latency_ms: number;
 limit: number;
 location_message?: string | null;
 location_not_found: boolean;
 location_resolved?: string | null;
 parsed: components["schemas"]["ParsedQueryInfo"];
 parsing_mode: string;
 query: string;
 requires_address: boolean;
 requires_auth: boolean;
 search_query_id?: string | null;
 skipped_operations?: string[];
 soft_filter_message?: string | null;
 soft_filtering_used: boolean;
 total_results: number;
 };
 NLSearchResponse: {
 meta: components["schemas"]["NLSearchMeta"];
 results: components["schemas"]["NLSearchResultItem"][];
 };
 NLSearchResultItem: {
 best_match: components["schemas"]["ServiceMatch"];
 coverage_areas?: string[];
 distance_km?: number | null;
 distance_mi?: number | null;
 instructor: components["schemas"]["InstructorSummary"];
 instructor_id: string;
 other_matches?: components["schemas"]["ServiceMatch"][];
 rating: components["schemas"]["RatingSummary"];
 relevance_score: number;
 total_matching_services: number;
 };
 NYCZipCheckResponse: {
 borough?: string | null;
 is_nyc: boolean;
 };
 NeighborhoodItem: {
 borough?: string | null;
 code?: string | null;
 id: string;
 name: string;
 };
 NeighborhoodsListResponse: {
 items: components["schemas"]["NeighborhoodItem"][];
 page?: number | null;
 per_page?: number | null;
 total: number;
 };
 NextAvailableSlotResponse: {
 date?: string | null;
 duration_minutes?: number | null;
 end_time?: string | null;
 found: boolean;
 message?: string | null;
 start_time?: string | null;
 };
 NoShowDisputeRequest: {
 reason: string;
 };
 NoShowDisputeResponse: {
 booking_id: string;
 disputed: boolean;
 requires_platform_review: boolean;
 success: boolean;
 };
 NoShowReportRequest: {
 no_show_type: "instructor" | "student";
 reason?: string | null;
 };
 NoShowReportResponse: {
 booking_id: string;
 dispute_window_ends: string;
 no_show_type: string;
 payment_status: string;
 success: boolean;
 };
 NotificationListResponse: {
 notifications: components["schemas"]["NotificationResponse"][];
 total: number;
 unread_count: number;
 };
 NotificationResponse: {
 body: string | null;
 category: string;
 created_at: string;
 data: {
 [key: string]: unknown;
 } | null;
 id: string;
 read_at: string | null;
 title: string;
 type: string;
 };
 NotificationStatusResponse: {
 message?: string | null;
 success: boolean;
 };
 NotificationUnreadCountResponse: {
 unread_count: number;
 };
 OnboardingResponse: {
 account_id: string;
 already_onboarded: boolean;
 onboarding_url: string;
 };
 OnboardingStatusResponse: {
 charges_enabled: boolean;
 details_submitted: boolean;
 has_account: boolean;
 onboarding_completed: boolean;
 payouts_enabled: boolean;
 requirements?: string[];
 };
 OperationResult: {
 action: string;
 operation_index: number;
 reason?: string | null;
 slot_id?: string | null;
 status: "success" | "failed" | "skipped";
 };
 OverridePayload: {
 action: "approve" | "reject";
 };
 PaginatedResponse_BookingResponse_: {
 has_next: boolean;
 has_prev: boolean;
 items: components["schemas"]["BookingResponse"][];
 page: number;
 per_page: number;
 total: number;
 };
 PaginatedResponse_InstructorProfileResponse_: {
 has_next: boolean;
 has_prev: boolean;
 items: components["schemas"]["InstructorProfileResponse"][];
 page: number;
 per_page: number;
 total: number;
 };
 PaginatedResponse_UpcomingBookingResponse_: {
 has_next: boolean;
 has_prev: boolean;
 items: components["schemas"]["UpcomingBookingResponse"][];
 page: number;
 per_page: number;
 total: number;
 };
 ParsedQueryInfo: {
 audience_hint?: string | null;
 date?: string | null;
 lesson_type?: string | null;
 location?: string | null;
 max_price?: number | null;
 service_query: string;
 skill_level?: string | null;
 time_after?: string | null;
 time_before?: string | null;
 urgency?: string | null;
 use_user_location: boolean;
 };
 PasswordChangeRequest: {
 current_password: string;
 new_password: string;
 };
 PasswordChangeResponse: {
 message: string;
 };
 PasswordResetConfirm: {
 new_password: string;
 token: string;
 };
 PasswordResetRequest: {
 email: string;
 };
 PasswordResetResponse: {
 message: string;
 };
 PasswordResetVerifyResponse: {
 [key: string]: unknown;
 };
 PaymentHealthCheckTriggerResponse: {
 message: string;
 status: string;
 task_id: string;
 timestamp: string;
 };
 PaymentHealthResponse: {
 alerts: string[];
 metrics: {
 [key: string]: number;
 };
 minutes_since_last_auth?: number | null;
 overdue_authorizations: number;
 payment_stats: {
 [key: string]: number;
 };
 recent_events: {
 [key: string]: number;
 };
 status: string;
 timestamp: string;
 };
 PaymentMethodResponse: {
 brand: string;
 created_at: string;
 id: string;
 is_default: boolean;
 last4: string;
 };
 PaymentSummary: {
 credit_applied: number;
 lesson_amount: number;
 service_fee: number;
 subtotal: number;
 tip_amount: number;
 tip_last_updated?: string | null;
 tip_paid: number;
 tip_status?: string | null;
 total_paid: number;
 };
 PayoutHistoryResponse: {
 payout_count: number;
 payouts?: components["schemas"]["PayoutSummary"][];
 total_paid_cents: number;
 total_pending_cents: number;
 };
 PayoutScheduleResponse: {
 account_id?: string | null;
 ok: boolean;
 settings?: {
 [key: string]: unknown;
 } | null;
 };
 PayoutSummary: {
 amount_cents: number;
 arrival_date?: string | null;
 created_at: string;
 failure_code?: string | null;
 failure_message?: string | null;
 id: string;
 status: string;
 };
 PerformanceMetrics: {
 avg_results_per_search: number;
 most_effective_type: string;
 zero_result_rate: number;
 };
 PerformanceMetricsResponse: {
 availability_service: components["schemas"]["ServiceMetrics"];
 booking_service: components["schemas"]["ServiceMetrics"];
 cache: {
 [key: string]: unknown;
 };
 conflict_checker: components["schemas"]["ServiceMetrics"];
 database: {
 [key: string]: unknown;
 };
 system: {
 [key: string]: number;
 };
 };
 PerformanceRecommendation: {
 action: string;
 message: string;
 severity: string;
 type: string;
 };
 PhoneUpdateRequest: {
 phone_number: string;
 };
 PhoneUpdateResponse: {
 phone_number?: string | null;
 verified: boolean;
 };
 PhoneVerifyConfirmRequest: {
 code: string;
 };
 PhoneVerifyResponse: {
 sent: boolean;
 verified: boolean;
 };
 PipelineStage: {
 details?: {
 [key: string]: unknown;
 } | null;
 duration_ms: number;
 name: string;
 status: components["schemas"]["StageStatus"];
 };
 PlaceDetails: {
 city?: string | null;
 country?: string | null;
 formatted_address: string;
 latitude: number;
 longitude: number;
 postal_code?: string | null;
 provider_id: string;
 state?: string | null;
 street_name?: string | null;
 street_number?: string | null;
 };
 PlaceSuggestion: {
 description: string;
 place_id: string;
 provider: string;
 text: string;
 types: string[];
 };
 PlatformFees: {
 founding_instructor: number;
 student_booking_fee: number;
 tier_1: number;
 tier_2: number;
 tier_3: number;
 };
 PopularQueriesResponse: {
 queries: components["schemas"]["PopularQueryItem"][];
 };
 PopularQueryItem: {
 avg_latency_ms?: number | null;
 avg_results: number;
 count: number;
 query: string;
 };
 PopularSearch: {
 average_results: number;
 query: string;
 search_count: number;
 unique_users: number;
 };
 PopularSearchesResponse: components["schemas"]["PopularSearch"][];
 PreferenceResponse: {
 category: string;
 channel: string;
 enabled: boolean;
 id: string;
 locked: boolean;
 };
 PreferenceUpdate: {
 category: string;
 channel: string;
 enabled: boolean;
 };
 PreferencesByCategory: {
 learning_tips: {
 [key: string]: boolean;
 };
 lesson_updates: {
 [key: string]: boolean;
 };
 messages: {
 [key: string]: boolean;
 };
 promotional: {
 [key: string]: boolean;
 };
 system_updates: {
 [key: string]: boolean;
 };
 };
 PreferredPublicSpaceIn: {
 address: string;
 label?: string | null;
 };
 PreferredPublicSpaceOut: {
 [key: string]: unknown;
 };
 PreferredTeachingLocationIn: {
 address: string;
 label?: string | null;
 };
 PreferredTeachingLocationOut: {
 [key: string]: unknown;
 };
 PriceFloorConfig: {
 private_in_person: number;
 private_remote: number;
 };
 PricingConfig: {
 founding_instructor_cap: number;
 founding_instructor_rate_pct: number;
 founding_search_boost: number;
 instructor_tiers: components["schemas"]["TierConfig"][];
 price_floor_cents: components["schemas"]["PriceFloorConfig"];
 student_credit_cycle: components["schemas"]["StudentCreditCycle"];
 student_fee_pct: number;
 tier_activity_window_days: number;
 tier_inactivity_reset_days: number;
 tier_stepdown_max: number;
 };
 PricingConfigPayload: {
 founding_instructor_cap: number;
 founding_instructor_rate_pct: number;
 founding_search_boost: number;
 instructor_tiers: components["schemas"]["TierConfig"][];
 price_floor_cents: components["schemas"]["PriceFloorConfig"];
 student_credit_cycle: components["schemas"]["StudentCreditCycle"];
 student_fee_pct: number;
 tier_activity_window_days: number;
 tier_inactivity_reset_days: number;
 tier_stepdown_max: number;
 };
 PricingConfigResponse: {
 config: components["schemas"]["PricingConfig"];
 updated_at?: string | null;
 };
 PricingPreviewIn: {
 applied_credit_cents: number;
 booking_date: string;
 instructor_id: string;
 instructor_service_id: string;
 location_type: string;
 meeting_location: string;
 selected_duration: number;
 start_time: string;
 };
 PricingPreviewOut: {
 application_fee_cents: number;
 base_price_cents: number;
 credit_applied_cents: number;
 instructor_platform_fee_cents: number;
 instructor_tier_pct: number;
 line_items: components["schemas"]["LineItem"][];
 student_fee_cents: number;
 student_pay_cents: number;
 target_instructor_payout_cents: number;
 top_up_transfer_cents: number;
 };
 PrivacyStatisticsResponse: {
 statistics: {
 [key: string]: unknown;
 };
 status: string;
 };
 ProblematicQuery: {
 avg_results: number;
 count: number;
 query: string;
 };
 ProfilePictureUrlsResponse: {
 urls: {
 [key: string]: string | null;
 };
 };
 ProxyUploadResponse: {
 ok: boolean;
 url?: string | null;
 };
 PublicConfigResponse: {
 fees: components["schemas"]["PlatformFees"];
 updated_at?: string | null;
 };
 PublicDayAvailability: {
 available_slots?: components["schemas"]["PublicTimeSlot"][];
 date: string;
 is_blackout: boolean;
 };
 PublicInstructorAvailability: {
 availability_by_date?: {
 [key: string]: components["schemas"]["PublicDayAvailability"];
 } | null;
 availability_summary?: {
 [key: string]: {
 [key: string]: unknown;
 };
 } | null;
 detail_level: string;
 earliest_available_date?: string | null;
 has_availability?: boolean | null;
 instructor_first_name?: string | null;
 instructor_id: string;
 instructor_last_initial?: string | null;
 timezone: string;
 total_available_days?: number | null;
 total_available_slots?: number | null;
 };
 PublicTimeSlot: {
 end_time: string;
 start_time: string;
 };
 PushStatusResponse: {
 message: string;
 success: boolean;
 };
 PushSubscribeRequest: {
 auth: string;
 endpoint: string;
 p256dh: string;
 user_agent?: string | null;
 };
 PushSubscriptionResponse: {
 created_at: string;
 endpoint: string;
 id: string;
 user_agent: string | null;
 };
 PushUnsubscribeRequest: {
 endpoint: string;
 };
 RateLimitResetResponse: {
 limits_reset: number;
 message: string;
 pattern: string;
 status: string;
 };
 RateLimitStats: {
 breakdown_by_type: {
 [key: string]: number;
 };
 top_limited_clients: {
 [key: string]: unknown;
 }[];
 total_keys: number;
 };
 RateLimitTestResponse: {
 message: string;
 note: string;
 timestamp: string;
 };
 RatingSummary: {
 average?: number | null;
 count: number;
 };
 RatingsBatchItem: {
 instructor_id: string;
 rating: number | null;
 review_count: number;
 };
 RatingsBatchRequest: {
 instructor_ids: string[];
 };
 RatingsBatchResponse: {
 results: components["schemas"]["RatingsBatchItem"][];
 };
 ReactionInfo: {
 emoji: string;
 user_id: string;
 };
 ReactionRequest: {
 emoji: string;
 };
 ReadReceiptEntry: {
 read_at: string;
 user_id: string;
 };
 ReadyProbeResponse: {
 notifications_healthy?: boolean | null;
 status: "ok" | "db_not_ready" | "cache_not_ready" | "degraded";
 };
 RecentAlertsResponse: {
 alerts: components["schemas"]["AlertDetail"][];
 hours: number;
 total: number;
 };
 RedisCeleryQueuesResponse: {
 queues: {
 [key: string]: unknown;
 };
 };
 RedisConnectionAuditResponse: {
 connections: {
 [key: string]: unknown;
 }[];
 };
 RedisFlushQueuesResponse: {
 message: string;
 queues_flushed: string[];
 };
 RedisHealthResponse: {
 connected: boolean;
 error?: string | null;
 status: string;
 };
 RedisStatsResponse: {
 stats: {
 [key: string]: unknown;
 };
 };
 RedisTestResponse: {
 connected_clients: number | null;
 error?: string | null;
 message?: string | null;
 ping?: boolean | null;
 redis_version: string | null;
 status: string;
 uptime_seconds: number | null;
 };
 ReferralClaimRequest: {
 code: string;
 };
 ReferralClaimResponse: {
 attributed: boolean;
 reason?: string | null;
 };
 ReferralErrorResponse: {
 reason: string;
 };
 ReferralLedgerResponse: {
 code: string;
 expiry_notice_days: number[];
 pending: components["schemas"]["RewardOut"][];
 redeemed: components["schemas"]["RewardOut"][];
 share_url: string;
 unlocked: components["schemas"]["RewardOut"][];
 };
 ReferralResolveResponse: {
 code: string;
 ok: boolean;
 redirect: string;
 };
 ReferralSendError: {
 email: string;
 error: string;
 };
 ReferralSendRequest: {
 emails: string[];
 from_name?: string | null;
 referral_link: string;
 };
 ReferralSendResponse: {
 errors?: components["schemas"]["ReferralSendError"][];
 failed: number;
 sent: number;
 status: string;
 };
 RequestMetrics: {
 active_count: number;
 average_response_time_ms: number;
 total_count: number;
 };
 RescheduledFromInfo: {
 booking_date: string;
 id: string;
 start_time: string;
 };
 ResultDistribution: {
 "1_5_results": number;
 "6_10_results": number;
 over_10_results: number;
 zero_results: number;
 };
 RetentionPolicyResponse: {
 message: string;
 stats: {
 [key: string]: unknown;
 };
 status: string;
 };
 RetryPaymentResponse: {
 error?: string | null;
 failure_count: number;
 payment_status: string;
 success: boolean;
 };
 ReviewItem: {
 created_at: string;
 id: string;
 instructor_service_id: string;
 rating: number;
 review_text: string | null;
 reviewer_display_name?: string | null;
 };
 ReviewListPageResponse: {
 has_next: boolean;
 has_prev: boolean;
 page: number;
 per_page: number;
 reviews: components["schemas"]["ReviewItem"][];
 total: number;
 };
 ReviewResponseModel: {
 created_at: string;
 id: string;
 instructor_id: string;
 response_text: string;
 review_id: string;
 };
 ReviewSubmitRequest: {
 booking_id: string;
 rating: number;
 review_text?: string | null;
 tip_amount_cents?: number | null;
 };
 ReviewSubmitResponse: {
 created_at: string;
 id: string;
 instructor_service_id: string;
 rating: number;
 review_text: string | null;
 reviewer_display_name?: string | null;
 tip_client_secret?: string | null;
 tip_status?: string | null;
 };
 RewardOut: {
 amount_cents: number;
 created_at: string;
 expire_ts?: string | null;
 id: string;
 side: components["schemas"]["RewardSide"];
 status: components["schemas"]["RewardStatus"];
 unlock_ts?: string | null;
 };
 RewardSide: "student" | "instructor";
 RewardStatus: "pending" | "unlocked" | "redeemed" | "void";
 SavePaymentMethodRequest: {
 payment_method_id: string;
 set_as_default: boolean;
 };
 SearchAnalyticsSummaryResponse: {
 conversions: {
 [key: string]: unknown;
 };
 date_range: components["schemas"]["DateRange"];
 performance: components["schemas"]["PerformanceMetrics"];
 search_types: {
 [key: string]: components["schemas"]["SearchTypeMetrics"];
 };
 totals: components["schemas"]["SearchTotals"];
 users: components["schemas"]["UserBreakdown"];
 };
 SearchClickRequest: {
 action: string;
 instructor_id: string;
 position: number;
 search_query_id: string;
 service_id?: string | null;
 };
 SearchClickResponse: {
 click_id: string;
 };
 SearchConfigResetResponse: {
 config: components["schemas"]["SearchConfigResponse"];
 status: string;
 };
 SearchConfigResponse: {
 available_embedding_models: components["schemas"]["ModelOption"][];
 available_parsing_models: components["schemas"]["ModelOption"][];
 embedding_model: string;
 embedding_timeout_ms: number;
 parsing_model: string;
 parsing_timeout_ms: number;
 };
 SearchConfigUpdate: {
 embedding_model?: string | null;
 embedding_timeout_ms?: number | null;
 parsing_model?: string | null;
 parsing_timeout_ms?: number | null;
 };
 SearchDiagnostics: {
 after_availability_filter: number;
 after_location_filter: number;
 after_price_filter: number;
 after_text_search: number;
 after_vector_search: number;
 budget: components["schemas"]["BudgetInfo"];
 cache_hit: boolean;
 embedding_used: boolean;
 final_results: number;
 initial_candidates: number;
 location_resolution?: components["schemas"]["LocationResolutionInfo"] | null;
 parsing_mode: string;
 pipeline_stages?: components["schemas"]["PipelineStage"][];
 total_latency_ms: number;
 vector_search_used: boolean;
 };
 SearchEffectiveness: {
 avg_results_per_search: number;
 median_results: number;
 searches_with_results: number;
 zero_result_rate: number;
 };
 SearchHealthCache: {
 available: boolean;
 error?: string | null;
 response_cache_version?: number | null;
 ttls?: {
 [key: string]: number;
 } | null;
 };
 SearchHealthComponents: {
 cache: components["schemas"]["SearchHealthCache"];
 embedding_circuit: string;
 parsing_circuit: string;
 };
 SearchHealthResponse: {
 components: components["schemas"]["SearchHealthComponents"];
 status: string;
 };
 SearchHistoryCreate: {
 device_context?: {
 [key: string]: unknown;
 } | null;
 guest_session_id?: string | null;
 observability_candidates?: {
 [key: string]: unknown;
 }[] | null;
 results_count?: number | null;
 search_context?: {
 [key: string]: unknown;
 } | null;
 search_query: string;
 search_type: string;
 };
 SearchHistoryResponse: {
 first_searched_at: string;
 guest_session_id?: string | null;
 id: string;
 last_searched_at: string;
 results_count?: number | null;
 search_count: number;
 search_event_id?: string | null;
 search_query: string;
 search_type: string;
 };
 SearchInteractionResponse: {
 interaction_id: string;
 message: string;
 status: string;
 success: boolean;
 };
 SearchMetricsResponse: {
 avg_latency_ms: number;
 avg_results: number;
 cache_hit_rate: number;
 degradation_rate: number;
 p50_latency_ms: number;
 p95_latency_ms: number;
 total_searches: number;
 zero_result_rate: number;
 };
 SearchPerformanceResponse: {
 effectiveness: components["schemas"]["SearchEffectiveness"];
 problematic_queries: components["schemas"]["ProblematicQuery"][];
 result_distribution: components["schemas"]["ResultDistribution"];
 };
 SearchRatingResponse: {
 is_service_specific: boolean;
 primary_rating: number | null;
 review_count: number;
 };
 SearchReferrer: {
 page: string;
 search_count: number;
 search_types: string[];
 unique_sessions: number;
 };
 SearchReferrersResponse: components["schemas"]["SearchReferrer"][];
 SearchTotals: {
 deleted_searches: number;
 deletion_rate: number;
 total_searches: number;
 total_users: number;
 unique_guests: number;
 unique_users: number;
 };
 SearchTrendsResponse: components["schemas"]["DailySearchTrend"][];
 SearchTypeMetrics: {
 count: number;
 percentage: number;
 };
 SendMessageRequest: {
 booking_id?: string | null;
 content: string;
 };
 SendMessageResponse: {
 created_at: string;
 id: string;
 };
 SendRemindersResponse: {
 failed_reminders: number;
 message: string;
 reminders_sent: number;
 };
 ServiceAreaItem: {
 borough?: string | null;
 name?: string | null;
 neighborhood_id: string;
 ntacode?: string | null;
 };
 ServiceAreaNeighborhood: {
 borough?: string | null;
 name?: string | null;
 neighborhood_id: string;
 ntacode?: string | null;
 };
 ServiceAreasResponse: {
 items: components["schemas"]["ServiceAreaItem"][];
 total: number;
 };
 ServiceAreasUpdateRequest: {
 neighborhood_ids: string[];
 };
 ServiceCreate: {
 age_groups?: string[] | null;
 description?: string | null;
 duration_options: number[];
 equipment_required?: string[] | null;
 hourly_rate: number | string;
 levels_taught?: string[] | null;
 location_types?: string[] | null;
 requirements?: string | null;
 service_catalog_id: string;
 };
 ServiceInfo: {
 description: string | null;
 id: string;
 name: string;
 };
 ServiceMatch: {
 description?: string | null;
 name: string;
 price_per_hour: number;
 relevance_score: number;
 service_catalog_id: string;
 service_id: string;
 };
 ServiceMetrics: {
 cache_operations: number;
 db_operations: number;
 operations: {
 [key: string]: number;
 };
 total_operations: number;
 };
 ServiceResponse: {
 age_groups?: string[] | null;
 description?: string | null;
 display_order?: number | null;
 duration_options: number[];
 equipment_required?: string[] | null;
 hourly_rate: number;
 id: string;
 is_active?: boolean | null;
 levels_taught?: string[] | null;
 location_types?: string[] | null;
 name?: string | null;
 online_capable?: boolean | null;
 requirements?: string | null;
 requires_certification?: boolean | null;
 service_catalog_id: string;
 service_catalog_name: string;
 };
 ServiceSearchMetadata: {
 active_instructors: number;
 filters_applied?: {
 [key: string]: unknown;
 };
 pagination?: {
 [key: string]: unknown;
 };
 total_matches: number;
 };
 ServiceSearchResponse: {
 instructors?: {
 [key: string]: unknown;
 }[];
 metadata: components["schemas"]["ServiceSearchMetadata"];
 query: string;
 search_type: "service";
 };
 SignedUploadResponse: {
 expires_at: string;
 headers?: {
 [key: string]: string;
 };
 object_key: string;
 public_url?: string | null;
 upload_url: string;
 };
 SlotOperation: {
 action: "add" | "remove" | "update";
 date?: string | null;
 end_time?: string | null;
 slot_id?: string | null;
 start_time?: string | null;
 };
 SlowQueriesResponse: {
 slow_queries: components["schemas"]["SlowQueryInfo"][];
 total_count: number;
 };
 SlowQueryInfo: {
 duration_ms: number;
 endpoint?: string | null;
 query: string;
 timestamp: string;
 };
 SlowRequestInfo: {
 duration_ms: number;
 method: string;
 path: string;
 status_code: number;
 timestamp: string;
 };
 SlowRequestsResponse: {
 slow_requests: components["schemas"]["SlowRequestInfo"][];
 total_count: number;
 };
 SpecificDateAvailabilityCreate: {
 end_time: string;
 specific_date: string;
 start_time: string;
 };
 StageStatus: "success" | "skipped" | "timeout" | "error" | "cache_hit" | "miss" | "cancelled";
 StudentBadgeView: {
 awarded_at?: string | null;
 confirmed_at?: string | null;
 description?: string | null;
 earned: boolean;
 name: string;
 progress?: components["schemas"]["BadgeProgressView"] | {
 [key: string]: unknown;
 } | null;
 slug: string;
 status?: string | null;
 };
 StudentCreditCycle: {
 cents10: number;
 cents20: number;
 cycle_len: number;
 mod10: number;
 mod20: number;
 };
 StudentInfo: {
 email: string;
 first_name: string;
 id: string;
 last_name: string;
 };
 SuccessResponse: {
 data?: {
 [key: string]: unknown;
 } | null;
 message: string;
 success: boolean;
 };
 TFADisableRequest: {
 current_password: string;
 };
 TFADisableResponse: {
 message: string;
 };
 TFASetupInitiateResponse: {
 otpauth_url: string;
 qr_code_data_url: string;
 secret: string;
 };
 TFASetupVerifyRequest: {
 code: string;
 };
 TFASetupVerifyResponse: {
 backup_codes: string[];
 enabled: boolean;
 };
 TFAStatusResponse: {
 enabled: boolean;
 last_used_at?: string | null;
 verified_at?: string | null;
 };
 TFAVerifyLoginRequest: {
 backup_code?: string | null;
 code?: string | null;
 temp_token: string;
 };
 TFAVerifyLoginResponse: {
 access_token: string;
 token_type: string;
 };
 TierConfig: {
 max?: number | null;
 min: number;
 pct: number;
 };
 TimeRange: {
 end_time: string;
 start_time: string;
 };
 TimeSlot: {
 end_time: string;
 start_time: string;
 };
 TopCategoryItem: {
 icon_name?: string | null;
 id: string;
 name: string;
 services?: components["schemas"]["TopCategoryServiceItem"][];
 slug: string;
 };
 TopCategoryServiceItem: {
 active_instructors: number;
 demand_score: number;
 display_order?: number | null;
 id: string;
 is_trending: boolean;
 name: string;
 slug: string;
 };
 TopReferrerOut: {
 code?: string | null;
 count: number;
 user_id: string;
 };
 TopServicesMetadata: {
 cached_for_seconds: number;
 services_per_category: number;
 total_categories: number;
 updated_at: string;
 };
 TopServicesPerCategoryResponse: {
 categories?: components["schemas"]["TopCategoryItem"][];
 metadata: components["schemas"]["TopServicesMetadata"];
 };
 TransactionHistoryItem: {
 booking_date: string;
 booking_id: string;
 created_at: string;
 credit_applied: number;
 duration_minutes: number;
 end_time: string;
 hourly_rate: number;
 id: string;
 instructor_name: string;
 lesson_amount: number;
 service_fee: number;
 service_name: string;
 start_time: string;
 status: string;
 tip_amount: number;
 tip_paid: number;
 tip_status?: string | null;
 total_paid: number;
 };
 TypingRequest: {
 is_typing: boolean;
 };
 UnreadCountResponse: {
 unread_count: number;
 user_id: string;
 };
 UpcomingBookingResponse: {
 booking_date: string;
 end_time: string;
 id: string;
 instructor_first_name: string;
 instructor_id: string;
 instructor_last_name: string;
 meeting_location: string | null;
 service_name: string;
 start_time: string;
 student_first_name: string;
 student_last_name: string;
 total_price: number;
 };
 UpdateConversationStateRequest: {
 state: "active" | "archived" | "trashed";
 };
 UpdateConversationStateResponse: {
 id: string;
 state: "active" | "archived" | "trashed";
 };
 UpdatePreferenceRequest: {
 enabled: boolean;
 };
 UserBasicPrivacy: {
 first_name: string;
 id: string;
 last_initial: string;
 };
 UserBreakdown: {
 authenticated: number;
 converted_guests: number;
 guest_percentage: number;
 guests: number;
 user_percentage: number;
 };
 UserCreate: {
 email: string;
 first_name: string;
 guest_session_id?: string | null;
 is_active: boolean | null;
 last_name: string;
 metadata?: {
 [key: string]: unknown;
 } | null;
 password: string;
 phone?: string | null;
 role?: string | null;
 timezone: string | null;
 zip_code: string;
 };
 UserDataDeletionRequest: {
 delete_account: boolean;
 };
 UserDataDeletionResponse: {
 account_deleted: boolean;
 deletion_stats: {
 [key: string]: number;
 };
 message: string;
 status: string;
 };
 UserLogin: {
 captcha_token?: string | null;
 email: string;
 guest_session_id?: string | null;
 password: string;
 };
 UserSummary: {
 first_name: string;
 id: string;
 last_initial: string;
 profile_photo_url?: string | null;
 };
 UserUpdate: {
 first_name?: string | null;
 last_name?: string | null;
 phone?: string | null;
 timezone?: string | null;
 zip_code?: string | null;
 };
 ValidateWeekRequest: {
 current_week: {
 [key: string]: components["schemas"]["TimeSlot"][];
 };
 saved_week: {
 [key: string]: components["schemas"]["TimeSlot"][];
 };
 week_start: string;
 };
 ValidationError: {
 loc: (string | number)[];
 msg: string;
 type: string;
 };
 ValidationSlotDetail: {
 action: string;
 conflicts_with?: {
 [key: string]: unknown;
 }[] | null;
 date?: string | null;
 end_time?: string | null;
 operation_index: number;
 reason?: string | null;
 slot_id?: string | null;
 start_time?: string | null;
 };
 ValidationSummary: {
 estimated_changes: {
 [key: string]: number;
 };
 has_conflicts: boolean;
 invalid_operations: number;
 operations_by_type: {
 [key: string]: number;
 };
 total_operations: number;
 valid_operations: number;
 };
 VapidPublicKeyResponse: {
 public_key: string;
 };
 WebhookAckResponse: {
 ok: boolean;
 };
 WebhookResponse: {
 event_type: string;
 message?: string | null;
 status: string;
 };
 WeekAvailabilityResponse: {
 [key: string]: components["schemas"]["TimeRange"][];
 };
 WeekAvailabilityUpdateResponse: {
 days_written: number;
 edited_dates?: string[];
 message: string;
 skipped_dates?: string[];
 skipped_past_window: number;
 version?: string | null;
 week_end: string;
 week_start: string;
 week_version?: string | null;
 weeks_affected: number;
 windows_created: number;
 windows_deleted: number;
 windows_updated: number;
 };
 WeekSpecificScheduleCreate: {
 base_version?: string | null;
 clear_existing: boolean;
 override: boolean;
 schedule: {
 [key: string]: unknown;
 }[];
 version?: string | null;
 week_start?: string | null;
 };
 WeekValidationResponse: {
 details: components["schemas"]["ValidationSlotDetail"][];
 summary: components["schemas"]["ValidationSummary"];
 valid: boolean;
 warnings: string[];
 };
 ZeroResultQueriesResponse: {
 queries: components["schemas"]["ZeroResultQueryItem"][];
 };
 ZeroResultQueryItem: {
 count: number;
 last_searched: string;
 query: string;
 };
 app__schemas__address_responses__DeleteResponse: {
 message: string;
 success: boolean;
 };
 app__schemas__availability_window__BulkUpdateRequest: {
 operations: components["schemas"]["SlotOperation"][];
 validate_only: boolean;
 };
 app__schemas__base_responses__DeleteResponse: {
 deleted_at?: string;
 message: string;
 success: boolean;
 };
 app__schemas__notification_preferences__BulkUpdateRequest: {
 updates: components["schemas"]["PreferenceUpdate"][];
 };
 app__schemas__payment_schemas__DeleteResponse: {
 success: boolean;
 };
 };
 responses: never;
 parameters: never;
 requestBodies: never;
 headers: never;
 pathItems: never;
};
export type $defs = Record<string, never>;
export interface operations {
 disable_api_v1_2fa_disable_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["TFADisableRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TFADisableResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 regenerate_backup_codes_api_v1_2fa_regenerate_backup_codes_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BackupCodesResponse"];
 };
 };
 };
 };
 setup_initiate_api_v1_2fa_setup_initiate_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TFASetupInitiateResponse"];
 };
 };
 };
 };
 setup_verify_api_v1_2fa_setup_verify_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["TFASetupVerifyRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TFASetupVerifyResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 status_endpoint_api_v1_2fa_status_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TFAStatusResponse"];
 };
 };
 };
 };
 verify_login_api_v1_2fa_verify_login_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["TFAVerifyLoginRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TFAVerifyLoginResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 deactivate_account_api_v1_account_deactivate_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AccountStatusChangeResponse"];
 };
 };
 };
 };
 get_phone_number_api_v1_account_phone_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PhoneUpdateResponse"];
 };
 };
 };
 };
 update_phone_number_api_v1_account_phone_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PhoneUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PhoneUpdateResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_phone_verification_api_v1_account_phone_verify_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PhoneVerifyResponse"];
 };
 };
 };
 };
 confirm_phone_verification_api_v1_account_phone_verify_confirm_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PhoneVerifyConfirmRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PhoneVerifyResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 reactivate_account_api_v1_account_reactivate_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AccountStatusChangeResponse"];
 };
 };
 };
 };
 check_account_status_api_v1_account_status_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AccountStatusResponse"];
 };
 };
 };
 };
 suspend_account_api_v1_account_suspend_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AccountStatusChangeResponse"];
 };
 };
 };
 };
 get_bulk_coverage_geojson_api_v1_addresses_coverage_bulk_get: {
 parameters: {
 query: {
 ids: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CoverageFeatureCollectionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_my_addresses_api_v1_addresses_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AddressListResponse"];
 };
 };
 };
 };
 create_my_address_api_v1_addresses_me_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AddressCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AddressResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_my_address_api_v1_addresses_me__address_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 address_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["app__schemas__address_responses__DeleteResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 update_my_address_api_v1_addresses_me__address_id__patch: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 address_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AddressUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AddressResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 places_autocomplete_api_v1_addresses_places_autocomplete_get: {
 parameters: {
 query: {
 q: string;
 provider?: string | null;
 scope?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AutocompleteResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 place_details_api_v1_addresses_places_details_get: {
 parameters: {
 query: {
 place_id: string;
 provider?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PlaceDetails"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_neighborhoods_api_v1_addresses_regions_neighborhoods_get: {
 parameters: {
 query?: {
 region_type?: string;
 borough?: string | null;
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NeighborhoodsListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_my_service_areas_api_v1_addresses_service_areas_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ServiceAreasResponse"];
 };
 };
 };
 };
 replace_my_service_areas_api_v1_addresses_service_areas_me_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ServiceAreasUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ServiceAreasResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 is_nyc_zip_api_v1_addresses_zip_is_nyc_get: {
 parameters: {
 query: {
 zip: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NYCZipCheckResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_audit_logs_api_v1_admin_audit_get: {
 parameters: {
 query?: {
 entity_type?: string | null;
 entity_id?: string | null;
 action?: string | null;
 actor_id?: string | null;
 actor_role?: string | null;
 start?: string | null;
 end?: string | null;
 limit?: number;
 offset?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AuditLogListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_admin_audit_log_api_v1_admin_audit_log_get: {
 parameters: {
 query?: {
 action?: string[] | null;
 admin_id?: string | null;
 date_from?: string | null;
 date_to?: string | null;
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminAuditLogResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_cases_api_v1_admin_background_checks_cases_get: {
 parameters: {
 query?: {
 status?: string;
 q?: string | null;
 page?: number;
 page_size?: number;
 limit?: number | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCCaseListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 admin_latest_consent_api_v1_admin_background_checks_consent__instructor_id__latest_get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCLatestConsentResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_counts_api_v1_admin_background_checks_counts_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCCaseCountsResponse"];
 };
 };
 };
 };
 bgc_expiring_api_v1_admin_background_checks_expiring_get: {
 parameters: {
 query?: {
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCExpiringItem"][];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_history_api_v1_admin_background_checks_history__instructor_id__get: {
 parameters: {
 query?: {
 limit?: number;
 cursor?: string | null;
 };
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCHistoryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_review_list_api_v1_admin_background_checks_review_get: {
 parameters: {
 query?: {
 limit?: number;
 cursor?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCReviewListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_review_count_api_v1_admin_background_checks_review_count_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCReviewCountResponse"];
 };
 };
 };
 };
 bgc_webhook_logs_api_v1_admin_background_checks_webhooks_get: {
 parameters: {
 query?: {
 limit?: number;
 cursor?: string | null;
 event?: string[];
 status?: string[];
 q?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCWebhookLogListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_webhook_stats_api_v1_admin_background_checks_webhooks_stats_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCWebhookStatsResponse"];
 };
 };
 };
 };
 open_bgc_dispute_api_v1_admin_background_checks__instructor_id__dispute_open_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": {
 [key: string]: unknown;
 };
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCDisputeResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 resolve_bgc_dispute_api_v1_admin_background_checks__instructor_id__dispute_resolve_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": {
 [key: string]: unknown;
 };
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCDisputeResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bgc_review_override_api_v1_admin_background_checks__instructor_id__override_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["OverridePayload"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BGCOverrideResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_pending_awards_api_v1_admin_badges_pending_get: {
 parameters: {
 query?: {
 before?: string | null;
 status?: string | null;
 limit?: number;
 offset?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminAwardListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 confirm_award_api_v1_admin_badges__award_id__confirm_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 award_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminAwardSchema"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 revoke_award_api_v1_admin_badges__award_id__revoke_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 award_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminAwardSchema"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_admin_bookings_api_v1_admin_bookings_get: {
 parameters: {
 query?: {
 search?: string | null;
 status?: string[] | null;
 payment_status?: string[] | null;
 date_from?: string | null;
 date_to?: string | null;
 needs_action?: boolean | null;
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminBookingListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_admin_booking_stats_api_v1_admin_bookings_stats_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminBookingStatsResponse"];
 };
 };
 };
 };
 get_admin_booking_detail_api_v1_admin_bookings__booking_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminBookingDetailResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 admin_cancel_booking_api_v1_admin_bookings__booking_id__cancel_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AdminCancelBookingRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminCancelBookingResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 admin_update_booking_status_api_v1_admin_bookings__booking_id__complete_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AdminBookingStatusUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminBookingStatusUpdateResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 resolve_no_show_api_v1_admin_bookings__booking_id__no_show_resolve_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AdminNoShowResolutionRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminNoShowResolutionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 admin_refund_booking_api_v1_admin_bookings__booking_id__refund_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AdminRefundRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminRefundResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_pricing_config_api_v1_admin_config_pricing_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PricingConfigResponse"];
 };
 };
 };
 };
 update_pricing_config_api_v1_admin_config_pricing_patch: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PricingConfigPayload"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PricingConfigResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 founding_instructor_count_api_v1_admin_instructors_founding_count_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["FoundingCountResponse"];
 };
 };
 };
 };
 admin_instructor_detail_api_v1_admin_instructors__instructor_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminInstructorDetailResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_referral_config_api_v1_admin_referrals_config_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminReferralsConfigOut"];
 };
 };
 };
 };
 get_referral_health_api_v1_admin_referrals_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminReferralsHealthOut"];
 };
 };
 };
 };
 get_referral_summary_api_v1_admin_referrals_summary_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminReferralsSummaryOut"];
 };
 };
 };
 };
 get_search_config_admin_api_v1_admin_search_config_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminSearchConfigResponse"];
 };
 };
 };
 };
 update_search_config_admin_api_v1_admin_search_config_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AdminSearchConfigUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminSearchConfigResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 reset_search_config_admin_api_v1_admin_search_config_reset_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AdminSearchConfigResponse"];
 };
 };
 };
 };
 get_codebase_metrics_history_api_v1_analytics_codebase_history_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CodebaseHistoryResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 append_codebase_metrics_history_api_v1_analytics_codebase_history_append_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AppendHistoryResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_codebase_metrics_api_v1_analytics_codebase_metrics_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CodebaseMetricsResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 export_analytics_api_v1_analytics_export_post: {
 parameters: {
 query?: {
 format?: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ExportAnalyticsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 candidates_category_trends_api_v1_analytics_search_candidates_category_trends_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CandidateCategoryTrendsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 candidate_service_queries_api_v1_analytics_search_candidates_queries_get: {
 parameters: {
 query: {
 service_catalog_id: string;
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CandidateServiceQueriesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 candidates_score_distribution_api_v1_analytics_search_candidates_score_distribution_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CandidateScoreDistributionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 candidates_summary_api_v1_analytics_search_candidates_summary_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CandidateSummaryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 candidates_top_services_api_v1_analytics_search_candidates_top_services_get: {
 parameters: {
 query?: {
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CandidateTopServicesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_conversion_metrics_api_v1_analytics_search_conversion_metrics_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ConversionMetricsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_popular_searches_api_v1_analytics_search_popular_searches_get: {
 parameters: {
 query?: {
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PopularSearchesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_search_referrers_api_v1_analytics_search_referrers_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchReferrersResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_search_analytics_summary_api_v1_analytics_search_search_analytics_summary_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchAnalyticsSummaryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_search_performance_api_v1_analytics_search_search_performance_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchPerformanceResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_search_trends_api_v1_analytics_search_search_trends_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchTrendsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 change_password_api_v1_auth_change_password_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PasswordChangeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PasswordChangeResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 login_api_v1_auth_login_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/x-www-form-urlencoded": components["schemas"]["Body_login_api_v1_auth_login_post"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["LoginResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 login_with_session_api_v1_auth_login_with_session_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UserLogin"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["LoginResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 read_users_me_api_v1_auth_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AuthUserWithPermissionsResponse"];
 };
 };
 };
 };
 update_current_user_api_v1_auth_me_patch: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UserUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AuthUserWithPermissionsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 register_api_v1_auth_register_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UserCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AuthUserResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 consume_invite_api_v1_beta_invites_consume_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InviteConsumeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AccessGrantResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 generate_invites_api_v1_beta_invites_generate_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InviteGenerateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteGenerateResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_invite_api_v1_beta_invites_send_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InviteSendRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteSendResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_invite_batch_api_v1_beta_invites_send_batch_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InviteBatchSendRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteBatchSendResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_invite_batch_async_api_v1_beta_invites_send_batch_async_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InviteBatchSendRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteBatchAsyncStartResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_invite_batch_progress_api_v1_beta_invites_send_batch_progress_get: {
 parameters: {
 query: {
 task_id: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteBatchProgressResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 validate_invite_api_v1_beta_invites_validate_get: {
 parameters: {
 query?: {
 code?: string | null;
 invite_code?: string | null;
 email?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InviteValidateResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 invite_verified_api_v1_beta_invites_verified_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_beta_metrics_summary_api_v1_beta_metrics_summary_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BetaMetricsSummaryResponse"];
 };
 };
 };
 };
 get_beta_settings_api_v1_beta_settings_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BetaSettingsResponse"];
 };
 };
 };
 };
 update_beta_settings_api_v1_beta_settings_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BetaSettingsUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BetaSettingsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_bookings_api_v1_bookings_get: {
 parameters: {
 query?: {
 status?: components["schemas"]["BookingStatus"] | null;
 upcoming_only?: boolean | null;
 upcoming?: boolean | null;
 exclude_future_confirmed?: boolean;
 include_past_confirmed?: boolean;
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_BookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_booking_api_v1_bookings_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingCreateResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 409: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 check_availability_api_v1_bookings_check_availability_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AvailabilityCheckRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AvailabilityCheckResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_reminder_emails_api_v1_bookings_send_reminders_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SendRemindersResponse"];
 };
 };
 };
 };
 get_booking_stats_api_v1_bookings_stats_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingStatsResponse"];
 };
 };
 };
 };
 get_upcoming_bookings_api_v1_bookings_upcoming_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_UpcomingBookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_booking_details_api_v1_bookings__booking_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 update_booking_api_v1_bookings__booking_id__patch: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 cancel_booking_api_v1_bookings__booking_id__cancel_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingCancel"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 complete_booking_api_v1_bookings__booking_id__complete_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 confirm_booking_payment_api_v1_bookings__booking_id__confirm_payment_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingConfirmPayment"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 report_no_show_api_v1_bookings__booking_id__no_show_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["NoShowReportRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NoShowReportResponse"];
 };
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 dispute_no_show_api_v1_bookings__booking_id__no_show_dispute_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["NoShowDisputeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NoShowDisputeResponse"];
 };
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 update_booking_payment_method_api_v1_bookings__booking_id__payment_method_patch: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingPaymentMethodUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_booking_preview_api_v1_bookings__booking_id__preview_get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingPreviewResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_booking_pricing_api_v1_bookings__booking_id__pricing_get: {
 parameters: {
 query?: {
 applied_credit_cents?: number;
 };
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PricingPreviewOut"];
 };
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 reschedule_booking_api_v1_bookings__booking_id__reschedule_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BookingRescheduleRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 409: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 retry_payment_authorization_api_v1_bookings__booking_id__retry_payment_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RetryPaymentResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_public_pricing_config_api_v1_config_pricing_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PricingConfigResponse"];
 };
 };
 };
 };
 get_public_config_api_v1_config_public_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PublicConfigResponse"];
 };
 };
 };
 };
 list_conversations_api_v1_conversations_get: {
 parameters: {
 query?: {
 state?: string | null;
 limit?: number;
 cursor?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ConversationListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_conversation_api_v1_conversations_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["CreateConversationRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CreateConversationResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_conversation_api_v1_conversations__conversation_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 conversation_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ConversationDetail"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_messages_api_v1_conversations__conversation_id__messages_get: {
 parameters: {
 query?: {
 limit?: number;
 before?: string | null;
 booking_id?: string | null;
 };
 header?: never;
 path: {
 conversation_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MessagesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_message_api_v1_conversations__conversation_id__messages_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 conversation_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["SendMessageRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SendMessageResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 update_conversation_state_api_v1_conversations__conversation_id__state_put: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 conversation_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UpdateConversationStateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["UpdateConversationStateResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 send_typing_indicator_api_v1_conversations__conversation_id__typing_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 conversation_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["TypingRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SuccessResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 database_health_api_v1_database_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DatabaseHealthResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 database_pool_status_api_v1_database_pool_status_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DatabasePoolStatusResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 database_stats_api_v1_database_stats_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DatabaseStatsResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_favorites_api_v1_favorites_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["FavoritesList"];
 };
 };
 };
 };
 check_favorite_status_api_v1_favorites_check__instructor_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["FavoriteStatusResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 add_favorite_api_v1_favorites__instructor_id__post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["FavoriteResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 remove_favorite_api_v1_favorites__instructor_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["FavoriteResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 gated_ping_api_v1_gated_ping_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["GatedPingResponse"];
 };
 };
 };
 };
 health_check_api_v1_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HealthResponse"];
 };
 };
 };
 };
 health_check_lite_api_v1_health_lite_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HealthLiteResponse"];
 };
 };
 };
 };
 rate_limit_test_api_v1_health_rate_limit_test_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HealthLiteResponse"];
 };
 };
 };
 };
 list_instructor_bookings_api_v1_instructor_bookings_get: {
 parameters: {
 query?: {
 status?: components["schemas"]["BookingStatus"] | null;
 upcoming?: boolean;
 exclude_future_confirmed?: boolean;
 page?: number;
 per_page?: number;
 include_past_confirmed?: boolean;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_BookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_completed_bookings_api_v1_instructor_bookings_completed_get: {
 parameters: {
 query?: {
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_BookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_pending_completion_bookings_api_v1_instructor_bookings_pending_completion_get: {
 parameters: {
 query?: {
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_BookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_upcoming_bookings_api_v1_instructor_bookings_upcoming_get: {
 parameters: {
 query?: {
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_BookingResponse_"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 mark_lesson_complete_api_v1_instructor_bookings__booking_id__complete_post: {
 parameters: {
 query?: {
 notes?: string | null;
 };
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 dispute_completion_api_v1_instructor_bookings__booking_id__dispute_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["Body_dispute_completion_api_v1_instructor_bookings__booking_id__dispute_post"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookingResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_instructors_api_v1_instructors_get: {
 parameters: {
 query: {
 service_catalog_id: string;
 min_price?: number;
 max_price?: number;
 age_group?: string;
 page?: number;
 per_page?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaginatedResponse_InstructorProfileResponse_"];
 };
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_all_availability_api_v1_instructors_availability_get: {
 parameters: {
 query?: {
 start_date?: string | null;
 end_date?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AvailabilityWindowResponse"][];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 apply_to_date_range_api_v1_instructors_availability_apply_to_date_range_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ApplyToDateRangeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ApplyToDateRangeResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_blackout_dates_api_v1_instructors_availability_blackout_dates_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BlackoutDateResponse"][];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 add_blackout_date_api_v1_instructors_availability_blackout_dates_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["BlackoutDateCreate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BlackoutDateResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_blackout_date_api_v1_instructors_availability_blackout_dates__blackout_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 blackout_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DeleteBlackoutResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 bulk_update_availability_api_v1_instructors_availability_bulk_update_patch: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["app__schemas__availability_window__BulkUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BulkUpdateResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 410: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 copy_week_availability_api_v1_instructors_availability_copy_week_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["CopyWeekRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CopyWeekResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 add_specific_date_availability_api_v1_instructors_availability_specific_date_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["SpecificDateAvailabilityCreate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AvailabilityWindowResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_week_availability_api_v1_instructors_availability_week_get: {
 parameters: {
 query: {
 start_date: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["WeekAvailabilityResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 save_week_availability_api_v1_instructors_availability_week_post: {
 parameters: {
 query?: {
 override?: boolean;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["WeekSpecificScheduleCreate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["WeekAvailabilityUpdateResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 409: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_week_booked_slots_api_v1_instructors_availability_week_booked_slots_get: {
 parameters: {
 query: {
 start_date: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BookedSlotsResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 validate_week_changes_api_v1_instructors_availability_week_validate_changes_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ValidateWeekRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["WeekValidationResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_availability_window_api_v1_instructors_availability__window_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 window_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DeleteWindowResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 501: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 update_availability_window_api_v1_instructors_availability__window_id__patch: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 window_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["AvailabilityWindowUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AvailabilityWindowResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 501: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_my_profile_api_v1_instructors_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorProfileResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 update_profile_api_v1_instructors_me_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InstructorProfileUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorProfileResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_profile_api_v1_instructors_me_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InstructorProfileCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorProfileResponse"];
 };
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_profile_api_v1_instructors_me_delete: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 go_live_api_v1_instructors_me_go_live_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorProfileResponse"];
 };
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_instructor_api_v1_instructors__instructor_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorProfileResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 record_background_check_consent_api_v1_instructors__instructor_id__bgc_consent_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ConsentPayload"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ConsentResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 trigger_background_check_invite_api_v1_instructors__instructor_id__bgc_invite_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: {
 content: {
 "application/json": components["schemas"]["BackgroundCheckInviteRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BackgroundCheckInviteResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 mock_background_check_pass_api_v1_instructors__instructor_id__bgc_mock_pass_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MockStatusResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 mock_background_check_reset_api_v1_instructors__instructor_id__bgc_mock_reset_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MockStatusResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 mock_background_check_review_api_v1_instructors__instructor_id__bgc_mock_review_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MockStatusResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 trigger_background_check_recheck_api_v1_instructors__instructor_id__bgc_recheck_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BackgroundCheckInviteResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_background_check_status_api_v1_instructors__instructor_id__bgc_status_get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["BackgroundCheckStatusResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_coverage_api_v1_instructors__instructor_id__coverage_get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CoverageFeatureCollectionResponse"];
 };
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_message_config_api_v1_messages_config_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MessageConfigResponse"];
 };
 };
 };
 };
 mark_messages_as_read_api_v1_messages_mark_read_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["MarkMessagesReadRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MarkMessagesReadResponse"];
 };
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 stream_user_messages_api_v1_messages_stream_get: {
 parameters: {
 query?: {
 sse_token?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": unknown;
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 429: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 get_unread_count_api_v1_messages_unread_count_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["UnreadCountResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 delete_message_api_v1_messages__message_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 message_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DeleteMessageResponse"];
 };
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 edit_message_api_v1_messages__message_id__patch: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 message_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["EditMessageRequest"];
 };
 };
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 400: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 add_reaction_api_v1_messages__message_id__reactions_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 message_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ReactionRequest"];
 };
 };
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 remove_reaction_api_v1_messages__message_id__reactions_delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 message_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ReactionRequest"];
 };
 };
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 401: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 403: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 acknowledge_alert_api_v1_monitoring_alerts_acknowledge__alert_type__post: {
 parameters: {
 query?: never;
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path: {
 alert_type: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AlertAcknowledgeResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_live_alerts_api_v1_monitoring_alerts_live_get: {
 parameters: {
 query?: {
 minutes?: number;
 };
 header: {
 "x-api-key": string;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["LiveAlertsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_recent_alerts_api_v1_monitoring_alerts_recent_get: {
 parameters: {
 query?: {
 hours?: number;
 limit?: number;
 severity?: string | null;
 };
 header: {
 "x-api-key": string;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RecentAlertsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_alert_summary_api_v1_monitoring_alerts_summary_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header: {
 "x-api-key": string;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AlertSummaryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_extended_cache_stats_api_v1_monitoring_cache_extended_stats_get: {
 parameters: {
 query?: never;
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ExtendedCacheStats"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_monitoring_dashboard_api_v1_monitoring_dashboard_get: {
 parameters: {
 query?: never;
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["MonitoringDashboardResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_payment_system_health_api_v1_monitoring_payment_health_get: {
 parameters: {
 query?: never;
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaymentHealthResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_slow_queries_api_v1_monitoring_slow_queries_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SlowQueriesResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_slow_requests_api_v1_monitoring_slow_requests_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SlowRequestsResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 trigger_payment_health_check_api_v1_monitoring_trigger_payment_health_check_post: {
 parameters: {
 query?: never;
 header?: {
 "X-Monitoring-API-Key"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaymentHealthCheckTriggerResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_preferences_api_v1_notification_preferences_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PreferencesByCategory"];
 };
 };
 };
 };
 update_preferences_bulk_api_v1_notification_preferences_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["app__schemas__notification_preferences__BulkUpdateRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PreferenceResponse"][];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 update_preference_api_v1_notification_preferences__category___channel__put: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 category: string;
 channel: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UpdatePreferenceRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PreferenceResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_notifications_api_v1_notifications_get: {
 parameters: {
 query?: {
 limit?: number;
 offset?: number;
 unread_only?: boolean;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationListResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_all_notifications_api_v1_notifications_delete: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationStatusResponse"];
 };
 };
 };
 };
 mark_all_notifications_read_api_v1_notifications_read_all_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationStatusResponse"];
 };
 };
 };
 };
 get_unread_count_api_v1_notifications_unread_count_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationUnreadCountResponse"];
 };
 };
 };
 };
 delete_notification_api_v1_notifications__notification_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 notification_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationStatusResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 mark_notification_read_api_v1_notifications__notification_id__read_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 notification_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NotificationStatusResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_cache_metrics_api_v1_ops_cache_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CacheMetricsResponse"];
 };
 };
 };
 };
 get_availability_cache_metrics_api_v1_ops_cache_availability_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AvailabilityCacheMetricsResponse"];
 };
 };
 };
 };
 reset_cache_stats_api_v1_ops_cache_reset_stats_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SuccessResponse"];
 };
 };
 };
 };
 health_check_api_v1_ops_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HealthCheckResponse"];
 };
 };
 };
 };
 get_performance_metrics_api_v1_ops_performance_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PerformanceMetricsResponse"];
 };
 };
 };
 };
 get_rate_limit_stats_api_v1_ops_rate_limits_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RateLimitStats"];
 };
 };
 };
 };
 reset_rate_limits_api_v1_ops_rate_limits_reset_post: {
 parameters: {
 query: {
 pattern: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RateLimitResetResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 test_rate_limit_api_v1_ops_rate_limits_test_get: {
 parameters: {
 query?: {
 requests?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RateLimitTestResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_slow_queries_api_v1_ops_slow_queries_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SlowQueriesResponse"];
 };
 };
 };
 };
 confirm_password_reset_api_v1_password_reset_confirm_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PasswordResetConfirm"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PasswordResetResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 request_password_reset_api_v1_password_reset_request_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PasswordResetRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PasswordResetResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 verify_reset_token_api_v1_password_reset_verify__token__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 token: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PasswordResetVerifyResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_checkout_api_v1_payments_checkout_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["CreateCheckoutRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CheckoutResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_dashboard_link_api_v1_payments_connect_dashboard_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DashboardLinkResponse"];
 };
 };
 };
 };
 request_instant_payout_api_v1_payments_connect_instant_payout_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstantPayoutResponse"];
 };
 };
 };
 };
 start_onboarding_api_v1_payments_connect_onboard_post: {
 parameters: {
 query?: {
 return_to?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["OnboardingResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 set_payout_schedule_api_v1_payments_connect_payout_schedule_post: {
 parameters: {
 query?: {
 interval?: string;
 weekly_anchor?: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PayoutScheduleResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_onboarding_status_api_v1_payments_connect_status_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["OnboardingStatusResponse"];
 };
 };
 };
 };
 get_credit_balance_api_v1_payments_credits_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CreditBalanceResponse"];
 };
 };
 };
 };
 get_instructor_earnings_api_v1_payments_earnings_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["EarningsResponse"];
 };
 };
 };
 };
 export_instructor_earnings_api_v1_payments_earnings_export_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: {
 content: {
 "application/json": components["schemas"]["EarningsExportRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": unknown;
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 refresh_identity_status_api_v1_payments_identity_refresh_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["IdentityRefreshResponse"];
 };
 };
 };
 };
 create_identity_session_api_v1_payments_identity_session_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["IdentitySessionResponse"];
 };
 };
 };
 };
 list_payment_methods_api_v1_payments_methods_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaymentMethodResponse"][];
 };
 };
 };
 };
 save_payment_method_api_v1_payments_methods_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["SavePaymentMethodRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PaymentMethodResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_payment_method_api_v1_payments_methods__method_id__delete: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 method_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["app__schemas__payment_schemas__DeleteResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_instructor_payouts_api_v1_payments_payouts_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PayoutHistoryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_transaction_history_api_v1_payments_transactions_get: {
 parameters: {
 query?: {
 limit?: number;
 offset?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TransactionHistoryItem"][];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 handle_stripe_webhook_api_v1_payments_webhooks_stripe_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["WebhookResponse"];
 };
 };
 };
 };
 preview_selection_pricing_api_v1_pricing_preview_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PricingPreviewIn"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PricingPreviewOut"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_my_data_api_v1_privacy_delete_me_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UserDataDeletionRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["UserDataDeletionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_user_data_admin_api_v1_privacy_delete_user__user_id__post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 user_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["UserDataDeletionRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["UserDataDeletionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 export_my_data_api_v1_privacy_export_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DataExportResponse"];
 };
 };
 };
 };
 export_user_data_admin_api_v1_privacy_export_user__user_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 user_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["DataExportResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 apply_retention_policies_api_v1_privacy_retention_apply_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RetentionPolicyResponse"];
 };
 };
 };
 };
 get_privacy_statistics_api_v1_privacy_statistics_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PrivacyStatisticsResponse"];
 };
 };
 };
 };
 get_instructor_public_availability_api_v1_public_instructors__instructor_id__availability_get: {
 parameters: {
 query: {
 start_date: string;
 end_date?: string | null;
 };
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PublicInstructorAvailability"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_next_available_slot_api_v1_public_instructors__instructor_id__next_available_get: {
 parameters: {
 query?: {
 duration_minutes?: number;
 };
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NextAvailableSlotResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 public_logout_api_v1_public_logout_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": unknown;
 };
 };
 };
 };
 send_referral_invites_api_v1_public_referrals_send_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ReferralSendRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReferralSendResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_guest_session_api_v1_public_session_guest_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["GuestSessionResponse"];
 };
 };
 };
 };
 subscribe_to_push_api_v1_push_subscribe_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PushSubscribeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PushStatusResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_subscriptions_api_v1_push_subscriptions_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PushSubscriptionResponse"][];
 };
 };
 };
 };
 unsubscribe_from_push_api_v1_push_unsubscribe_delete: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["PushUnsubscribeRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PushStatusResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_vapid_public_key_api_v1_push_vapid_public_key_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["VapidPublicKeyResponse"];
 };
 };
 };
 };
 resolve_referral_slug_api_v1_r__slug__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 slug: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReferralResolveResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 ready_probe_api_v1_ready_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReadyProbeResponse"];
 };
 };
 };
 };
 celery_queue_status_api_v1_redis_celery_queues_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisCeleryQueuesResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 redis_connection_audit_api_v1_redis_connection_audit_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisConnectionAuditResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 flush_celery_queues_api_v1_redis_flush_queues_delete: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisFlushQueuesResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 redis_health_api_v1_redis_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisHealthResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 redis_stats_api_v1_redis_stats_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisStatsResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 redis_test_api_v1_redis_test_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RedisTestResponse"];
 };
 };
 404: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 };
 };
 apply_referral_credit_api_v1_referrals_checkout_apply_referral_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["CheckoutApplyRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CheckoutApplyResponse"] | components["schemas"]["ReferralErrorResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 claim_referral_code_api_v1_referrals_claim_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ReferralClaimRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReferralClaimResponse"] | components["schemas"]["ReferralErrorResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_my_referral_ledger_api_v1_referrals_me_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReferralLedgerResponse"];
 };
 };
 };
 };
 submit_review_api_v1_reviews_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["ReviewSubmitRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReviewSubmitResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_existing_reviews_for_bookings_api_v1_reviews_booking_existing_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": string[];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ExistingReviewIdsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_review_for_booking_api_v1_reviews_booking__booking_id__get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 booking_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReviewItem"] | null;
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_instructor_ratings_api_v1_reviews_instructor__instructor_id__ratings_get: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorRatingsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_recent_reviews_api_v1_reviews_instructor__instructor_id__recent_get: {
 parameters: {
 query?: {
 instructor_service_id?: string | null;
 limit?: number;
 page?: number;
 min_rating?: number | null;
 rating?: number | null;
 with_text?: boolean | null;
 };
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReviewListPageResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_search_rating_api_v1_reviews_instructor__instructor_id__search_rating_get: {
 parameters: {
 query?: {
 instructor_service_id?: string | null;
 };
 header?: never;
 path: {
 instructor_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchRatingResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_ratings_batch_api_v1_reviews_ratings_batch_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["RatingsBatchRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["RatingsBatchResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 respond_to_review_api_v1_reviews__review_id__respond_post: {
 parameters: {
 query?: never;
 header?: never;
 path: {
 review_id: string;
 };
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["Body_respond_to_review_api_v1_reviews__review_id__respond_post"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ReviewResponseModel"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 nl_search_api_v1_search_get: {
 parameters: {
 query: {
 q: string;
 lat?: number | null;
 lng?: number | null;
 region?: string;
 limit?: number;
 diagnostics?: boolean;
 force_skip_tier5?: boolean;
 force_skip_tier4?: boolean;
 force_skip_vector?: boolean;
 force_skip_embedding?: boolean;
 force_high_load?: boolean;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["NLSearchResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_recent_searches_api_v1_search_history_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: {
 "x-guest-session-id"?: string | null;
 "x-session-id"?: string | null;
 "x-search-origin"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchHistoryResponse"][];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 record_search_api_v1_search_history_post: {
 parameters: {
 query?: never;
 header?: {
 "x-guest-session-id"?: string | null;
 "x-session-id"?: string | null;
 "x-search-origin"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["SearchHistoryCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchHistoryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 record_guest_search_api_v1_search_history_guest_post: {
 parameters: {
 query?: never;
 header?: {
 "x-guest-session-id"?: string | null;
 "x-session-id"?: string | null;
 "x-search-origin"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["GuestSearchHistoryCreate"];
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchHistoryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 track_interaction_api_v1_search_history_interaction_post: {
 parameters: {
 query?: never;
 header?: {
 "x-guest-session-id"?: string | null;
 "x-session-id"?: string | null;
 "x-search-origin"?: string | null;
 };
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": {
 [key: string]: unknown;
 };
 };
 };
 responses: {
 201: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchInteractionResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_search_api_v1_search_history__search_id__delete: {
 parameters: {
 query?: never;
 header?: {
 "x-guest-session-id"?: string | null;
 };
 path: {
 search_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 204: {
 headers: {
 [name: string]: unknown;
 };
 content?: never;
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 search_metrics_api_v1_search_analytics_metrics_get: {
 parameters: {
 query?: {
 days?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchMetricsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 popular_queries_api_v1_search_analytics_popular_get: {
 parameters: {
 query?: {
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["PopularQueriesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 zero_result_queries_api_v1_search_analytics_zero_results_get: {
 parameters: {
 query?: {
 days?: number;
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ZeroResultQueriesResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 log_search_click_api_v1_search_click_post: {
 parameters: {
 query?: {
 search_query_id?: string | null;
 service_id?: string | null;
 instructor_id?: string | null;
 position?: number | null;
 action?: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: {
 content: {
 "application/json": components["schemas"]["SearchClickRequest"] | null;
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchClickResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_config_api_v1_search_config_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchConfigResponse"];
 };
 };
 };
 };
 update_config_api_v1_search_config_put: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["SearchConfigUpdate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchConfigResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 reset_config_api_v1_search_config_reset_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchConfigResetResponse"];
 };
 };
 };
 };
 search_health_api_v1_search_health_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SearchHealthResponse"];
 };
 };
 };
 };
 get_catalog_services_api_v1_services_catalog_get: {
 parameters: {
 query?: {
 category?: string | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CatalogServiceResponse"][];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_all_services_with_instructors_api_v1_services_catalog_all_with_instructors_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["AllServicesWithInstructorsResponse"];
 };
 };
 };
 };
 get_kids_available_services_api_v1_services_catalog_kids_available_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CatalogServiceMinimalResponse"][];
 };
 };
 };
 };
 get_top_services_per_category_api_v1_services_catalog_top_per_category_get: {
 parameters: {
 query?: {
 limit?: number;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["TopServicesPerCategoryResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_service_categories_api_v1_services_categories_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["CategoryResponse"][];
 };
 };
 };
 };
 add_service_to_profile_api_v1_services_instructor_add_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["InstructorServiceCreate"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["InstructorServiceResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 search_services_api_v1_services_search_get: {
 parameters: {
 query: {
 q: string;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ServiceSearchResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 list_student_badges_api_v1_students_badges_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["StudentBadgeView"][];
 };
 };
 };
 };
 list_earned_student_badges_api_v1_students_badges_earned_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["StudentBadgeView"][];
 };
 };
 };
 };
 list_in_progress_student_badges_api_v1_students_badges_progress_get: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["StudentBadgeView"][];
 };
 };
 };
 };
 finalize_profile_picture_api_v1_uploads_r2_finalize_profile_picture_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["FinalizeProfilePictureRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SuccessResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 proxy_upload_to_r2_api_v1_uploads_r2_proxy_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "multipart/form-data": components["schemas"]["Body_proxy_upload_to_r2_api_v1_uploads_r2_proxy_post"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ProxyUploadResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 create_signed_upload_api_v1_uploads_r2_signed_url_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["CreateSignedUploadRequest"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SignedUploadResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 upload_finalize_profile_picture_api_v1_users_me_profile_picture_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody: {
 content: {
 "application/json": components["schemas"]["FinalizeProfilePicturePayload"];
 };
 };
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SuccessResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 delete_profile_picture_api_v1_users_me_profile_picture_delete: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["app__schemas__base_responses__DeleteResponse"];
 };
 };
 };
 };
 get_profile_picture_urls_batch_api_v1_users_profile_picture_urls_get: {
 parameters: {
 query?: {
 ids?: string[];
 variant?: ("original" | "display" | "thumb") | null;
 };
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["ProfilePictureUrlsResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 get_profile_picture_url_api_v1_users__user_id__profile_picture_url_get: {
 parameters: {
 query?: {
 variant?: ("original" | "display" | "thumb") | null;
 };
 header?: never;
 path: {
 user_id: string;
 };
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["SuccessResponse"];
 };
 };
 422: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["HTTPValidationError"];
 };
 };
 };
 };
 handle_checkr_webhook_api_v1_webhooks_checkr_post: {
 parameters: {
 query?: never;
 header?: never;
 path?: never;
 cookie?: never;
 };
 requestBody?: never;
 responses: {
 200: {
 headers: {
 [name: string]: unknown;
 };
 content: {
 "application/json": components["schemas"]["WebhookAckResponse"];
 };
 };
 };
 };
}

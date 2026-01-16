from datetime import date, datetime, timezone

from app.repositories.search_analytics_repository import (
    CandidateServiceQueryData,
    CandidateSummaryData,
    CategoryTrendData,
    DailySearchTrendData,
    PopularSearchData,
    ProblematicQueryData,
    SearchEffectivenessData,
    SearchReferrerData,
    SearchTotalsData,
    SearchTypeBreakdown,
    TopServiceData,
)
from app.services.search_analytics_service import SearchAnalyticsService


class FakeSearchAnalyticsRepository:
    def __init__(self):
        self.trends = [
            DailySearchTrendData(date=date.today(), total_searches=10, unique_users=3, unique_guests=2)
        ]
        self.popular = [
            PopularSearchData(query="guitar", search_count=7, unique_users=4, average_results=5.5)
        ]
        self.referrers = [
            SearchReferrerData(referrer="/search", search_count=12, unique_sessions=9)
        ]
        self.totals = SearchTotalsData(total_searches=10, unique_users=4, unique_guests=3, avg_results=4.2)
        self.type_breakdown = [
            SearchTypeBreakdown(search_type="natural_language", count=7),
            SearchTypeBreakdown(search_type="keyword", count=3),
        ]
        self.deleted_searches = 2
        self.guest_sessions = 5
        self.converted_guests = 2
        self.zero_results = 1
        self.most_effective = [("natural_language", 0.8)]
        self.engaged_sessions = 3
        self.avg_searches = 2.5
        self.effectiveness = SearchEffectivenessData(avg_results=3.6, total_searches=10)
        self.searches_with_results = 9
        self.problematic = [ProblematicQueryData(query="bad query", count=2, avg_results=0.5)]
        self.candidate_summary = CandidateSummaryData(
            total_candidates=30,
            events_with_candidates=3,
            zero_result_events_with_candidates=1,
            source_breakdown={"vector": 20, "text": 10},
        )
        self.category_trends = [
            CategoryTrendData(date=date.today(), category="Music", count=5)
        ]
        self.top_services = [
            TopServiceData(
                service_catalog_id="svc1",
                service_name="Guitar",
                category_name="Music",
                candidate_count=10,
                avg_score=0.7,
                avg_position=1.5,
            )
        ]
        self.service_instructors = {"svc1": 2}
        self.service_queries = [
            CandidateServiceQueryData(
                searched_at=datetime.now(timezone.utc),
                search_query="guitar lessons",
                results_count=5,
                position=1,
                score=0.8,
                source="vector",
            )
        ]

    def get_search_trends(self, start, end):
        return self.trends

    def get_popular_searches(self, start, end, limit):
        return self.popular[:limit]

    def get_search_referrers(self, start, end):
        return self.referrers

    def get_search_totals(self, start, end):
        return self.totals

    def get_search_type_breakdown(self, start, end):
        return self.type_breakdown

    def count_deleted_searches(self, start, end):
        return self.deleted_searches

    def count_guest_sessions(self, start, end):
        return self.guest_sessions

    def count_converted_guests(self, start, end):
        return self.converted_guests

    def count_zero_result_searches(self, start, end):
        return self.zero_results

    def get_most_effective_search_type(self, start, end):
        return self.most_effective

    def count_engaged_guest_sessions(self, start, end):
        return self.engaged_sessions

    def get_avg_searches_per_guest(self, start, end):
        return self.avg_searches

    def count_searches_in_result_range(self, start, end, min_results, max_results=None):
        if min_results == 1 and max_results == 5:
            return 4
        if min_results == 6 and max_results == 10:
            return 3
        return 2

    def get_search_effectiveness(self, start, end):
        return self.effectiveness

    def count_searches_with_results(self, start, end):
        return self.searches_with_results

    def get_problematic_queries(self, start, end):
        return self.problematic

    def get_candidate_summary(self, start, end):
        return self.candidate_summary

    def get_candidate_category_trends(self, start, end):
        return self.category_trends

    def get_candidate_top_services(self, start, end, limit):
        return self.top_services[:limit]

    def get_service_instructor_counts(self, service_ids):
        return self.service_instructors

    def count_candidates_by_score_range(self, start, end, min_score, max_score=None):
        if min_score == 0.9:
            return 1
        if min_score == 0.8:
            return 2
        return 3

    def count_candidates_below_score(self, start, end, score):
        return 4

    def get_candidate_service_queries(self, service_catalog_id, start, end, limit):
        return self.service_queries[:limit]


def test_trends_popular_referrers():
    repo = FakeSearchAnalyticsRepository()
    service = SearchAnalyticsService(db=None, repository=repo)

    trends = service.get_search_trends(days=7)
    popular = service.get_popular_searches(days=7, limit=10)
    referrers = service.get_search_referrers(days=7)

    assert trends[0].total_searches == 10
    assert popular[0].query == "guitar"
    assert referrers[0].referrer == "/search"


def test_summary_and_conversion_metrics():
    repo = FakeSearchAnalyticsRepository()
    service = SearchAnalyticsService(db=None, repository=repo)

    summary = service.get_search_analytics_summary(days=7)
    conversions = service.get_conversion_metrics(days=7)

    assert summary["totals"]["total_searches"] == 10
    assert summary["users"]["converted_guests"] == 2
    assert summary["search_types"]["natural_language"]["count"] == 7
    assert conversions["guest_sessions"]["conversion_rate"] == 40.0


def test_search_performance_builds_problematic_queries():
    repo = FakeSearchAnalyticsRepository()
    service = SearchAnalyticsService(db=None, repository=repo)

    performance = service.get_search_performance(days=7)

    assert performance["result_distribution"]["zero_results"] == 1
    assert performance["effectiveness"]["searches_with_results"] == 9
    assert performance["problematic_queries"][0]["query"] == "bad query"


def test_candidate_analytics_outputs():
    repo = FakeSearchAnalyticsRepository()
    service = SearchAnalyticsService(db=None, repository=repo)

    summary = service.get_candidate_summary(days=30)
    trends = service.get_candidate_category_trends(days=30)
    top = service.get_candidate_top_services(days=30, limit=5)
    dist = service.get_candidate_score_distribution(days=30)
    queries = service.get_candidate_service_queries("svc1", days=30, limit=10)

    assert summary["avg_candidates_per_event"] == 10.0
    assert trends[0]["category"] == "Music"
    assert top[0]["opportunity_score"] == 5.0
    assert dist["gte_0_90"] == 1
    assert queries[0]["search_query"] == "guitar lessons"

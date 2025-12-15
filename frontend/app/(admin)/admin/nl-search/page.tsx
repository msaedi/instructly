// frontend/app/(admin)/admin/nl-search/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search,
  Settings,
  Clock,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Lock,
} from 'lucide-react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { logger } from '@/lib/logger';
import { fetchWithAuth } from '@/lib/api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';

// Types
interface ModelOption {
  id: string;
  name: string;
  description: string;
}

interface SearchConfig {
  parsing_model: string;
  parsing_timeout_ms: number;
  embedding_model: string;
  embedding_timeout_ms: number;
  available_parsing_models: ModelOption[];
  available_embedding_models: ModelOption[];
}

interface InstructorInfo {
  id: string;
  first_name: string;
  last_initial: string;
  profile_picture_url: string | null;
  bio_snippet: string | null;
  verified: boolean;
  years_experience: number | null;
}

interface RatingSummary {
  average: number | null;
  count: number;
}

interface ServiceMatch {
  service_id: string;
  service_catalog_id: string;
  name: string;
  description: string | null;
  price_per_hour: number;
  relevance_score: number;
}

interface SearchResult {
  instructor_id: string;
  instructor: InstructorInfo;
  rating: RatingSummary;
  coverage_areas: string[];
  best_match: ServiceMatch;
  other_matches: ServiceMatch[];
  total_matching_services: number;
  relevance_score: number;
  distance_km?: number | null;
  distance_mi?: number | null;
}

interface ParsedQuery {
  service_query: string;
  location: string | null;
  max_price: number | null;
  date: string | null;
  time_after: string | null;
  time_before?: string | null;
  audience_hint: string | null;
  skill_level: string | null;
  urgency: string | null;
}

interface SearchMeta {
  query: string;
  corrected_query?: string | null;
  parsed: ParsedQuery;
  total_results: number;
  limit: number;
  latency_ms: number;
  cache_hit: boolean;
  degraded: boolean;
  degradation_reasons: string[];
  parsing_mode: string;
  filters_applied?: string[];
  soft_filtering_used?: boolean;
  filter_stats?: FilterStats | null;
  soft_filter_message?: string | null;
  location_resolved?: string | null;
  location_not_found?: boolean;
}

interface SearchResponse {
  results: SearchResult[];
  meta: SearchMeta;
}

interface FilterStats {
  initial_candidates: number;
  after_price?: number;
  after_location?: number;
  after_availability?: number;
  after_soft_filtering?: number;
  final_candidates: number;
}

// API functions
async function fetchConfig(): Promise<SearchConfig> {
  const res = await fetchWithAuth('/api/v1/search/config');
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json() as Promise<SearchConfig>;
}

async function updateConfig(config: Partial<SearchConfig>): Promise<SearchConfig> {
  const res = await fetchWithAuth('/api/v1/search/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error('Failed to update config');
  return res.json() as Promise<SearchConfig>;
}

async function resetConfig(): Promise<SearchConfig> {
  const res = await fetchWithAuth('/api/v1/search/config/reset', {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to reset config');
  const data = (await res.json()) as { config: SearchConfig };
  return data.config;
}

async function executeSearch(query: string): Promise<SearchResponse> {
  const res = await fetchWithAuth(`/api/v1/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Search failed');
  return res.json() as Promise<SearchResponse>;
}

// Example queries for quick testing
const EXAMPLE_QUERIES = [
  'piano lessons',
  'cheap guitar lessons tomorrow',
  'yoga classes morning',
  'math tutoring for kids',
  'urgent swimming lessons',
  'violin lessons under $50',
  'SAT prep in brooklyn',
] as const;

export default function NLSearchAdminPage() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  // State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);

  // Fetch config
  const { data: config, isLoading: configLoading, error: configError } = useQuery({
    queryKey: ['search-config'],
    queryFn: fetchConfig,
  });

  // Update config mutation
  const configMutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['search-config'] });
    },
    onError: (error) => {
      logger.error('Failed to update config', error);
    },
  });

  // Reset config mutation
  const resetMutation = useMutation({
    mutationFn: resetConfig,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['search-config'] });
    },
  });

  // Handle search
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchError(null);
    try {
      const results = await executeSearch(searchQuery);
      setSearchResults(results);
    } catch (error) {
      logger.error('Search failed', error);
      setSearchError(error instanceof Error ? error.message : 'Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  // Handle config change
  const handleConfigChange = (field: string, value: string | number) => {
    configMutation.mutate({ [field]: value });
  };

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </Link>
              <h1 className="text-xl font-semibold">NL Search Testing</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setShowConfig(!showConfig)}
                className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-full transition-colors ${
                  showConfig
                    ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                    : 'text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60'
                }`}
              >
                <Settings className="h-4 w-4" />
                {showConfig ? 'Hide Config' : 'Show Config'}
              </button>
              <button
                onClick={() => void logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <div className="col-span-12 md:col-span-9 lg:col-span-9 space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
              <StatsCard
                title="Parsing Model"
                value={config?.parsing_model ?? 'Loading...'}
                icon={<Settings className="w-5 h-5 text-purple-600" />}
                loading={configLoading}
              />
              <StatsCard
                title="Embedding Model"
                value={config?.embedding_model?.split('-').slice(-1)[0] ?? 'Loading...'}
                icon={<Search className="w-5 h-5 text-blue-600" />}
                loading={configLoading}
              />
              <StatsCard
                title="Parse Timeout"
                value={`${config?.parsing_timeout_ms ?? 0}ms`}
                icon={<Clock className="w-5 h-5 text-amber-600" />}
                loading={configLoading}
              />
              <StatsCard
                title="Embed Timeout"
                value={`${config?.embedding_timeout_ms ?? 0}ms`}
                icon={<Clock className="w-5 h-5 text-green-600" />}
                loading={configLoading}
              />
            </div>

            {/* Config Error */}
            {configError && (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <div className="flex items-center">
                  <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400 mr-2" />
                  <p className="text-red-700 dark:text-red-300">
                    Failed to load config: {configError instanceof Error ? configError.message : 'Unknown error'}
                  </p>
                </div>
              </div>
            )}

            {/* Configuration Panel */}
            {showConfig && config && (
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Configuration</h2>
                  <button
                    onClick={() => resetMutation.mutate()}
                    disabled={resetMutation.isPending}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
                  >
                    <RefreshCw className={`h-4 w-4 ${resetMutation.isPending ? 'animate-spin' : ''}`} />
                    Reset to defaults
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  {/* Parsing Model */}
                  <div className="space-y-2">
                    <Label>Parsing Model</Label>
                    <Select
                      value={config.parsing_model}
                      onValueChange={(value) => handleConfigChange('parsing_model', value)}
                      disabled={configMutation.isPending}
                    >
                      <SelectTrigger className="w-full min-w-[280px] px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
                        {/* Show only model name when collapsed, not description */}
                        <SelectValue>
                          {config.available_parsing_models.find((m) => m.id === config.parsing_model)?.name ??
                            config.parsing_model}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="min-w-[400px]">
                        {config.available_parsing_models.map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            <div className="flex flex-col">
                              <span className="font-medium">{model.name}</span>
                              <span className="text-xs text-gray-500">{model.description}</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Parsing Timeout */}
                  <div className="space-y-2">
                    <Label htmlFor="parsing-timeout">Parsing Timeout (ms)</Label>
                    <input
                      id="parsing-timeout"
                      type="number"
                      value={config.parsing_timeout_ms}
                      onChange={(e) => handleConfigChange('parsing_timeout_ms', parseInt(e.target.value, 10))}
                      disabled={configMutation.isPending}
                      min={500}
                      max={10000}
                      step={100}
                      className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-300"
                    />
                  </div>

                  {/* Embedding Model (Read-only) */}
                  <div className="space-y-2">
                    <Label>Embedding Model</Label>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 px-3 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 flex items-center gap-2">
                        <Lock className="h-4 w-4 text-gray-400" />
                        <span>{config.embedding_model}</span>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Requires re-seeding to change. Run <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">python scripts/generate_openai_embeddings.py</code>
                    </p>
                  </div>

                  {/* Embedding Timeout */}
                  <div className="space-y-2">
                    <Label htmlFor="embedding-timeout">Embedding Timeout (ms)</Label>
                    <input
                      id="embedding-timeout"
                      type="number"
                      value={config.embedding_timeout_ms}
                      onChange={(e) => handleConfigChange('embedding_timeout_ms', parseInt(e.target.value, 10))}
                      disabled={configMutation.isPending}
                      min={500}
                      max={10000}
                      step={100}
                      className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-300"
                    />
                  </div>
                </div>

                <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                  Changes are temporary and will reset on server restart. To persist changes, update environment
                  variables.
                </p>
              </div>
            )}

            {/* Search Input */}
            <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Test Search</h2>

              <div className="flex gap-3">
                <div className="flex-1">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleSearch();
                    }}
                    placeholder="Try: piano lessons in brooklyn under $50 for kids"
                    className="w-full px-4 py-3 text-lg ring-1 ring-gray-300/70 dark:ring-gray-700/60 rounded-xl bg-white/60 dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-300"
                  />
                </div>
                <button
                  onClick={() => void handleSearch()}
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-6 py-3 text-white bg-purple-600 rounded-full hover:bg-purple-700 focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors shadow-sm"
                >
                  {isSearching ? (
                    <RefreshCw className="w-5 h-5 animate-spin" />
                  ) : (
                    <Search className="w-5 h-5" />
                  )}
                  Search
                </button>
              </div>

              {/* Example Queries */}
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="text-sm text-gray-500 dark:text-gray-400">Try:</span>
                {EXAMPLE_QUERIES.map((example) => (
                  <button
                    key={example}
                    onClick={() => setSearchQuery(example)}
                    className="px-2 py-1 text-xs text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 rounded hover:bg-indigo-100 dark:hover:bg-indigo-900/40"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Error */}
            {searchError && (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <div className="flex items-center">
                  <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400 mr-2" />
                  <p className="text-red-700 dark:text-red-300">{searchError}</p>
                </div>
              </div>
            )}

            {/* Search Results */}
            {searchResults && (
              <>
                {/* Diagnostics */}
                <DiagnosticsPanel meta={searchResults.meta} />

                {/* Soft Filter Message */}
                {searchResults.meta.soft_filtering_used && searchResults.meta.soft_filter_message && (
                  <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4 flex items-center gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                    <p className="text-sm text-amber-800 dark:text-amber-200">{searchResults.meta.soft_filter_message}</p>
                  </div>
                )}

                {/* Results List */}
                <ResultsPanel results={searchResults.results} totalResults={searchResults.meta.total_results} />
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// Stats Card Component
function StatsCard({
  title,
  value,
  icon,
  loading,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl p-4 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          {loading ? (
            <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mt-1" />
          ) : (
            <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{value}</p>
          )}
        </div>
        {icon}
      </div>
    </div>
  );
}

// Diagnostics Panel Component
function DiagnosticsPanel({ meta }: { meta: SearchMeta }) {
  const latencyStatus = meta.latency_ms < 200 ? 'good' : meta.latency_ms < 500 ? 'warning' : 'error';
  const parsedTime = formatParsedTimeWindow(meta.parsed.time_after, meta.parsed.time_before);

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Search Diagnostics</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <DiagnosticItem label="Latency" value={`${meta.latency_ms}ms`} status={latencyStatus} />
        <DiagnosticItem
          label="Cache Hit"
          value={meta.cache_hit ? 'Yes' : 'No'}
          status={meta.cache_hit ? 'good' : 'neutral'}
        />
        <DiagnosticItem label="Parsing Mode" value={meta.parsing_mode} status="neutral" />
        <DiagnosticItem
          label="Results"
          value={meta.total_results.toString()}
          status={meta.total_results > 0 ? 'good' : 'error'}
        />
      </div>

      {meta.degraded && (
        <div className="p-3 mb-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          <span className="text-sm text-amber-800 dark:text-amber-200">
            Degraded mode: {meta.degradation_reasons.join(', ')}
          </span>
        </div>
      )}

      {/* Parsed Query */}
      <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Parsed Query</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <ParsedField label="Service" value={meta.parsed.service_query} />
          <ParsedField label="Location" value={meta.parsed.location} />
          <ParsedField label="Resolved Location" value={meta.location_resolved ?? null} />
          <ParsedField label="Max Price" value={meta.parsed.max_price ? `$${meta.parsed.max_price}` : null} />
          <ParsedField label="Date" value={meta.parsed.date} />
          <ParsedField label="Time" value={parsedTime} />
          <ParsedField label="Audience" value={meta.parsed.audience_hint} />
          <ParsedField label="Skill Level" value={meta.parsed.skill_level} />
          <ParsedField label="Urgency" value={meta.parsed.urgency} />
        </div>
      </div>

      {/* Filter Funnel */}
      {meta.filter_stats && (
        <div className="p-4 mt-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter Funnel</h3>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {meta.soft_filtering_used ? 'Soft filtering used' : 'Hard filters only'}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <FunnelChip label="Initial" value={meta.filter_stats.initial_candidates} color="blue" />
            {meta.filter_stats.after_price !== undefined && (
              <FunnelChip label="After Price" value={meta.filter_stats.after_price} color="green" />
            )}
            {meta.filter_stats.after_location !== undefined && (
              <FunnelChip label="After Location" value={meta.filter_stats.after_location} color="yellow" />
            )}
            {meta.filter_stats.after_availability !== undefined && (
              <FunnelChip label="After Availability" value={meta.filter_stats.after_availability} color="purple" />
            )}
            {meta.filter_stats.after_soft_filtering !== undefined && (
              <FunnelChip label="After Soft" value={meta.filter_stats.after_soft_filtering} color="orange" />
            )}
            <FunnelChip label="Final" value={meta.filter_stats.final_candidates} color="emerald" />
          </div>
        </div>
      )}
    </div>
  );
}

function FunnelChip({
  label,
  value,
  color,
}: {
  label: string;
  value: number | undefined;
  color: 'blue' | 'green' | 'yellow' | 'purple' | 'orange' | 'emerald';
}) {
  const colorClasses = {
    blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
    green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
    yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
    purple: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
    orange: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
    emerald: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200',
  };

  return (
    <span className={`px-2 py-1 rounded ${colorClasses[color]}`}>
      {label}: {value ?? '-'}
    </span>
  );
}

// Diagnostic Item Component
function DiagnosticItem({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: 'good' | 'warning' | 'error' | 'neutral';
}) {
  const statusColors = {
    good: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20',
    warning: 'text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-900/20',
    error: 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20',
    neutral: 'text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-800/50',
  };

  return (
    <div className={`p-3 rounded-lg ${statusColors[status]}`}>
      <p className="text-xs opacity-75">{label}</p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}

// Parsed Field Component
function ParsedField({ label, value }: { label: string; value: string | number | null }) {
  if (value === null || value === undefined) {
    return (
      <div>
        <span className="text-gray-400">{label}:</span>
        <span className="ml-1 text-gray-300">-</span>
      </div>
    );
  }

  return (
    <div>
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>
      <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  );
}

function formatTime12h(time: string): string {
  const match = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
  if (!match) return time;

  const hours24 = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isFinite(hours24) || !Number.isFinite(minutes)) return time;

  const period = hours24 >= 12 ? 'pm' : 'am';
  const hours12 = hours24 % 12 === 0 ? 12 : hours24 % 12;

  if (minutes === 0) return `${hours12}${period}`;
  return `${hours12}:${minutes.toString().padStart(2, '0')}${period}`;
}

function formatParsedTimeWindow(
  timeAfter: string | null,
  timeBefore: string | null | undefined,
): string | null {
  if (!timeAfter && !timeBefore) return null;
  if (timeAfter && timeBefore) return `${formatTime12h(timeAfter)} - ${formatTime12h(timeBefore)}`;
  if (timeAfter) return `after ${formatTime12h(timeAfter)}`;
  return `before ${formatTime12h(timeBefore ?? '')}`;
}

// Results Panel Component
function ResultsPanel({ results, totalResults }: { results: SearchResult[]; totalResults: number }) {
  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Results ({totalResults})</h2>

      {results.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
          No results found. Try a different query.
        </div>
      ) : (
        <div className="space-y-4">
          {results.map((result, index) => (
            <ResultCard key={result.instructor_id ?? `result-${index}`} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}

// Result Card Component
function ResultCard({ result }: { result: SearchResult }) {
  const [showDetails, setShowDetails] = useState(false);
  const { instructor, best_match, rating, coverage_areas, relevance_score } = result;

  return (
    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/30 rounded">
              {(relevance_score * 100).toFixed(0)}%
            </span>
            <h3 className="font-medium text-gray-900 dark:text-gray-100">
              {instructor.first_name} {instructor.last_initial}.
              {instructor.verified && <span className="ml-1 text-blue-500">✓</span>}
            </h3>
            {result.distance_mi !== null && result.distance_mi !== undefined && (
              <span className="ml-1 px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded">
                {result.distance_mi.toFixed(1)} mi
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Best match: <span className="font-medium">{best_match.name}</span>
          </div>
          {instructor.bio_snippet && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 line-clamp-2">{instructor.bio_snippet}</p>
          )}
          <div className="mt-2 flex items-center gap-4 text-sm">
            <span className="font-medium text-green-600 dark:text-green-400">${best_match.price_per_hour}/hr</span>
            {rating.average && (
              <span className="text-gray-500 dark:text-gray-400">
                ★ {rating.average.toFixed(1)} ({rating.count} reviews)
              </span>
            )}
            {result.total_matching_services > 1 && (
              <span className="text-gray-500 dark:text-gray-400">
                +{result.total_matching_services - 1} more services
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center gap-1"
        >
          {showDetails ? (
            <>
              Hide <ChevronUp className="w-4 h-4" />
            </>
          ) : (
            <>
              Details <ChevronDown className="w-4 h-4" />
            </>
          )}
        </button>
      </div>

      {showDetails && (
        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 space-y-3">
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Instructor Info</h4>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
              <div>Years Experience: {instructor.years_experience ?? 'N/A'}</div>
              <div>Verified: {instructor.verified ? 'Yes' : 'No'}</div>
            </div>
          </div>

          {coverage_areas.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Coverage Areas</h4>
              <div className="flex flex-wrap gap-1">
                {coverage_areas.map((area) => (
                  <span key={area} className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 rounded">
                    {area}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.other_matches.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Other Matching Services</h4>
              <div className="space-y-1">
                {result.other_matches.map((match) => (
                  <div key={match.service_id} className="text-xs text-gray-500 dark:text-gray-400">
                    {match.name} - ${match.price_per_hour}/hr ({(match.relevance_score * 100).toFixed(0)}% match)
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-xs text-gray-400 dark:text-gray-500">
            Instructor ID: {result.instructor_id} | Service ID: {best_match.service_id}
          </div>
        </div>
      )}
    </div>
  );
}

'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Script from 'next/script';
import { BRAND } from '@/app/config/brand';
import { useAllServicesWithInstructors, useServiceCategories } from '@/hooks/queries/useServices';
import { withApiBase } from '@/lib/apiBase';
import { logger } from '@/lib/logger';
import type { ProfileFormState, ServiceAreaItem } from '@/features/instructor-profile/types';
import { ServiceAreasCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/ServiceAreasCard';
import { BioCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/BioCard';
import type { components } from '@/features/shared/api/types';

type NeighborhoodsListResponse = components['schemas']['NeighborhoodsListResponse'];

const WEBHOOK_URL = 'https://instainstru.app.n8n.cloud/webhook/instructor-lead';

const REFERRAL_OPTIONS = [
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'google_search', label: 'Google Search' },
  { value: 'friend_colleague', label: 'Friend/Colleague' },
  { value: 'instainstru_instructor', label: 'InstaInstru Instructor' },
  { value: 'other', label: 'Other' },
] as const;

type FormErrorKey =
  | 'firstName'
  | 'lastName'
  | 'email'
  | 'phone'
  | 'ageGroup'
  | 'category'
  | 'subcategory'
  | 'neighborhood'
  | 'hourlyRate'
  | 'experienceYears'
  | 'bio';

type FormErrors = Partial<Record<FormErrorKey, string>>;

type SubmitStatus = 'idle' | 'loading' | 'success' | 'error';

const NYC_BOROUGHS = ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const;

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const toTitle = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export default function InstructorApplyPage() {
  const { data: categoriesData, isLoading: categoriesLoading } = useServiceCategories();
  const { data: servicesData, isLoading: servicesLoading } = useAllServicesWithInstructors();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [category, setCategory] = useState('');
  const [subcategory, setSubcategory] = useState('');
  const [hourlyRate, setHourlyRate] = useState('');
  const [hasExistingClients, setHasExistingClients] = useState(false);
  const [referralSource, setReferralSource] = useState('');
  const [teachesKids, setTeachesKids] = useState(false);
  const [teachesAdults, setTeachesAdults] = useState(false);
  const [profile, setProfile] = useState<ProfileFormState>({
    first_name: '',
    last_name: '',
    postal_code: '',
    bio: '',
    service_area_boroughs: [],
    years_experience: 0,
  });
  const [bioTouched, setBioTouched] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [status, setStatus] = useState<SubmitStatus>('idle');
  const inFlightRef = useRef(false);

  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [openBoroughs, setOpenBoroughs] = useState<Set<string>>(new Set());
  const [globalNeighborhoodFilter, setGlobalNeighborhoodFilter] = useState('');
  const [idToItem, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});
  const boroughAccordionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const categories = useMemo(
    () => (Array.isArray(categoriesData) ? categoriesData : []),
    [categoriesData]
  );

  const subcategoryOptions = useMemo(() => {
    if (!category || !servicesData?.categories) return [];
    const match = servicesData.categories.find((item) => item.id === category);
    return match?.services || [];
  }, [category, servicesData?.categories]);

  useEffect(() => {
    if (!category) {
      setSubcategory('');
      return;
    }
    if (subcategory && !subcategoryOptions.some((service) => service.slug === subcategory)) {
      setSubcategory('');
    }
  }, [category, subcategory, subcategoryOptions]);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = withApiBase(`/api/v1/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`);
      const response = await fetch(url, { credentials: 'include' });
      if (response.ok) {
        const data = (await response.json()) as NeighborhoodsListResponse;
        const list = (data.items ?? []).flatMap((raw) => {
          const record = raw as Record<string, unknown>;
          const neighborhoodId =
            typeof record['neighborhood_id'] === 'string'
              ? (record['neighborhood_id'] as string)
              : typeof record['id'] === 'string'
              ? (record['id'] as string)
              : '';
          if (!neighborhoodId) return [];
          return [
            {
              neighborhood_id: neighborhoodId,
              ntacode:
                typeof record['ntacode'] === 'string'
                  ? (record['ntacode'] as string)
                  : typeof record['code'] === 'string'
                  ? (record['code'] as string)
                  : null,
              name: typeof record['name'] === 'string' ? (record['name'] as string) : null,
              borough: record['borough'] ?? null,
            } as ServiceAreaItem,
          ];
        });
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const item of list) {
            const id = item.neighborhood_id;
            if (id) next[id] = item;
          }
          return next;
        });
        return list;
      }
    } catch (error) {
      logger.warn('Failed to load neighborhood list', error as Error);
    }
    return boroughNeighborhoods[borough] || [];
  }, [boroughNeighborhoods]);

  useEffect(() => {
    NYC_BOROUGHS.forEach((borough) => {
      void loadBoroughNeighborhoods(borough);
    });
  }, [loadBoroughNeighborhoods]);

  useEffect(() => {
    if (globalNeighborhoodFilter.trim().length > 0) {
      NYC_BOROUGHS.forEach((borough) => {
        void loadBoroughNeighborhoods(borough);
      });
    }
  }, [globalNeighborhoodFilter, loadBoroughNeighborhoods]);

  const selectedNeighborhoodId = useMemo(() => Array.from(selectedNeighborhoods.values())[0] || '', [selectedNeighborhoods]);
  const selectedNeighborhoodName = selectedNeighborhoodId
    ? toTitle(String(idToItem[selectedNeighborhoodId]?.name || selectedNeighborhoodId))
    : '';

  const toggleNeighborhood = (id: string) => {
    setSelectedNeighborhoods((prev) => {
      if (prev.has(id)) return new Set();
      return new Set([id]);
    });
    clearError('neighborhood');
  };

  const toggleBoroughAccordion = async (borough: string) => {
    setOpenBoroughs((prev) => {
      const next = new Set(prev);
      if (next.has(borough)) next.delete(borough);
      else next.add(borough);
      return next;
    });
    await loadBoroughNeighborhoods(borough);
  };

  const toggleBoroughAll = async (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => {
    if (!value) {
      setSelectedNeighborhoods(new Set());
      return;
    }
    const list = itemsOverride || (await loadBoroughNeighborhoods(borough));
    const first = list[0]?.neighborhood_id;
    if (first) {
      setSelectedNeighborhoods(new Set([first]));
    }
  };

  const clearError = (key: FormErrorKey) => {
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const validate = (): FormErrors => {
    const nextErrors: FormErrors = {};
    if (!firstName.trim()) nextErrors.firstName = 'First name is required.';
    if (!lastName.trim()) nextErrors.lastName = 'Last name is required.';
    if (!email.trim()) nextErrors.email = 'Email is required.';
    else if (!emailPattern.test(email.trim())) nextErrors.email = 'Enter a valid email address.';
    if (!phone.trim()) nextErrors.phone = 'Phone number is required.';
    else if (phone.replace(/\D/g, '').length < 7) nextErrors.phone = 'Enter a valid phone number.';
    if (!teachesKids && !teachesAdults) nextErrors.ageGroup = 'Select at least one age group.';
    if (!category) nextErrors.category = 'Select a service category.';
    if (!subcategory) nextErrors.subcategory = 'Select a subcategory.';
    if (!selectedNeighborhoodId) nextErrors.neighborhood = 'Select your primary neighborhood.';

    const rateValue = hourlyRate.trim().length > 0 ? Number(hourlyRate) : null;
    if (rateValue !== null && (Number.isNaN(rateValue) || rateValue < 0 || rateValue > 500)) {
      nextErrors.hourlyRate = 'Hourly rate must be between $0 and $500.';
    }

    if (profile.years_experience < 0 || profile.years_experience > 70) {
      nextErrors.experienceYears = 'Years of experience must be between 0 and 70.';
    }

    if (profile.bio.length > 500) {
      nextErrors.bio = 'Bio must be 500 characters or less.';
    }

    return nextErrors;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const nextErrors = validate();
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    setStatus('loading');
    try {
      const payload = {
        instructor: {
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          phone: phone.trim(),
          category,
          subcategory,
          location: selectedNeighborhoodName || null,
          experience_years: profile.years_experience > 0 ? profile.years_experience : null,
          hourly_rate: hourlyRate.trim().length > 0 ? Number(hourlyRate) : null,
          bio: profile.bio.trim() || null,
          has_existing_clients: hasExistingClients,
          teaches_kids: teachesKids,
          teaches_adults: teachesAdults,
        },
        referral_source: referralSource || null,
        source: 'founding_instructor_application',
        submitted_at: new Date().toISOString(),
      };

      const response = await fetch(WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Webhook responded with ${response.status}`);
      }

      setStatus('success');
    } catch (error) {
      logger.error('Failed to submit founding instructor application', error as Error);
      setStatus('error');
    } finally {
      inFlightRef.current = false;
    }
  };

  return (
    <>
      <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative transition-colors duration-200">
        <div className="sm:mx-auto sm:w-full sm:max-w-3xl">
          <div className="bg-white/95 dark:bg-gray-900/80 py-10 px-4 shadow-[0_20px_40px_rgba(126,34,206,0.12)] rounded-[28px] border border-white/60 dark:border-gray-800/60 backdrop-blur-sm sm:px-8 transition-colors duration-200">
            <div className="text-center mb-8">
              <h1 className="text-4xl font-bold text-[#7E22CE] transition-colors">{BRAND.name}</h1>
              <h2 className="text-2xl font-bold mb-2 text-gray-900 dark:text-gray-100 mt-3">Founding Instructor Application</h2>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
                Share your teaching focus and we&apos;ll follow up within 24-48 hours.
              </p>
            </div>

            {status === 'success' ? (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center text-emerald-900">
                <p className="text-lg font-semibold">Application Received!</p>
                <p className="mt-3 text-sm text-emerald-800">
                  Thank you for applying to be a founding instructor. We&apos;re reviewing applications and will be in touch
                  within 24-48 hours. Check your inbox (and spam folder) for an email from teach@instainstru.com
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="first-name" className="block text-sm font-medium text-gray-700">
                      First Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="first-name"
                      type="text"
                      value={firstName}
                      onChange={(event) => {
                        setFirstName(event.target.value);
                        clearError('firstName');
                      }}
                      required
                      className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white text-gray-900"
                      placeholder="Jane"
                      aria-invalid={Boolean(errors.firstName)}
                      aria-describedby={errors.firstName ? 'first-name-error' : undefined}
                    />
                    {errors.firstName && (
                      <p id="first-name-error" className="mt-1 text-sm text-red-600">
                        {errors.firstName}
                      </p>
                    )}
                  </div>

                <div>
                  <label htmlFor="last-name" className="block text-sm font-medium text-gray-700">
                    Last Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="last-name"
                    type="text"
                    value={lastName}
                    onChange={(event) => {
                      setLastName(event.target.value);
                      clearError('lastName');
                    }}
                    required
                    className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white text-gray-900"
                    placeholder="Doe"
                    aria-invalid={Boolean(errors.lastName)}
                    aria-describedby={errors.lastName ? 'last-name-error' : undefined}
                  />
                  {errors.lastName && (
                    <p id="last-name-error" className="mt-1 text-sm text-red-600">
                      {errors.lastName}
                    </p>
                  )}
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                    Email <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      clearError('email');
                    }}
                    required
                    className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white text-gray-900"
                    placeholder="you@example.com"
                    aria-invalid={Boolean(errors.email)}
                    aria-describedby={errors.email ? 'email-error' : undefined}
                  />
                  {errors.email && (
                    <p id="email-error" className="mt-1 text-sm text-red-600">
                      {errors.email}
                    </p>
                  )}
                </div>

                <div>
                  <label htmlFor="phone" className="block text-sm font-medium text-gray-700">
                    Phone <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="phone"
                    type="tel"
                    inputMode="tel"
                    value={phone}
                    onChange={(event) => {
                      setPhone(event.target.value);
                      clearError('phone');
                    }}
                    required
                    className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white text-gray-900"
                    placeholder="(917) 555-0142"
                    aria-invalid={Boolean(errors.phone)}
                    aria-describedby={errors.phone ? 'phone-error' : undefined}
                  />
                  {errors.phone && (
                    <p id="phone-error" className="mt-1 text-sm text-red-600">
                      {errors.phone}
                    </p>
                  )}
                </div>

                <div>
                  <label htmlFor="hourly-rate" className="block text-sm font-medium text-gray-700">
                    Hourly Rate
                  </label>
                  <div className="relative mt-1">
                    <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
                    <input
                      id="hourly-rate"
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={500}
                      step={1}
                      value={hourlyRate}
                      onChange={(event) => {
                        setHourlyRate(event.target.value);
                        clearError('hourlyRate');
                      }}
                      className="block w-full px-3 py-2 h-10 pl-7 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white text-gray-900"
                      placeholder="95"
                      aria-invalid={Boolean(errors.hourlyRate)}
                      aria-describedby={errors.hourlyRate ? 'hourly-rate-error' : undefined}
                    />
                  </div>
                  {errors.hourlyRate && (
                    <p id="hourly-rate-error" className="mt-1 text-sm text-red-600">
                      {errors.hourlyRate}
                    </p>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="category" className="block text-sm font-medium text-gray-700">
                  Service Category <span className="text-rose-500">*</span>
                </label>
                <select
                  id="category"
                  value={category}
                  onChange={(event) => {
                    setCategory(event.target.value);
                    setSubcategory('');
                    clearError('category');
                    clearError('subcategory');
                  }}
                  required
                  disabled={categoriesLoading}
                  className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm bg-white text-gray-900 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] disabled:opacity-60"
                  aria-invalid={Boolean(errors.category)}
                  aria-describedby={errors.category ? 'category-error' : undefined}
                >
                  <option value="">{categoriesLoading ? 'Loading categories...' : 'Select a category'}</option>
                  {categories.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
                {errors.category && (
                  <p id="category-error" className="mt-1 text-sm text-red-600">
                    {errors.category}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="subcategory" className="block text-sm font-medium text-gray-700">
                  Subcategory <span className="text-rose-500">*</span>
                </label>
                <select
                  id="subcategory"
                  value={subcategory}
                  onChange={(event) => {
                    setSubcategory(event.target.value);
                    clearError('subcategory');
                  }}
                  required
                  disabled={!category || servicesLoading}
                  className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm bg-white text-gray-900 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] disabled:opacity-60"
                  aria-invalid={Boolean(errors.subcategory)}
                  aria-describedby={errors.subcategory ? 'subcategory-error' : undefined}
                >
                  <option value="">{servicesLoading ? 'Loading subcategories...' : 'Select a subcategory'}</option>
                  {subcategoryOptions.map((item) => (
                    <option key={item.slug ?? item.id} value={item.slug ?? ''}>{item.name}</option>
                  ))}
                </select>
                {errors.subcategory && (
                  <p id="subcategory-error" className="mt-1 text-sm text-red-600">
                    {errors.subcategory}
                  </p>
                )}
              </div>

              <div>
                <div className="bg-white rounded-lg p-4 border border-gray-200 dark:bg-gray-900/70 dark:border-gray-800/80">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">
                    Age Group <span className="text-rose-500">*</span>
                  </label>
                  <div className="flex gap-2">
                    {(['kids', 'adults'] as const).map((ageType) => {
                      const isSelected = ageType === 'kids' ? teachesKids : teachesAdults;
                      return (
                        <button
                          key={ageType}
                          type="button"
                          onClick={() => {
                            if (ageType === 'kids') {
                              setTeachesKids((prev) => !prev);
                            } else {
                              setTeachesAdults((prev) => !prev);
                            }
                            clearError('ageGroup');
                          }}
                          className={`flex-1 px-3 py-2 text-sm rounded-md transition-colors ${
                            isSelected
                              ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800/80 dark:text-gray-200 dark:hover:bg-gray-700/80'
                          }`}
                          aria-pressed={isSelected}
                        >
                          {ageType === 'kids' ? 'Kids' : 'Adults'}
                        </button>
                      );
                    })}
                  </div>
                </div>
                {errors.ageGroup && (
                  <p className="mt-2 text-sm text-red-600" id="age-group-error">
                    {errors.ageGroup}
                  </p>
                )}
              </div>

              <div>
                <ServiceAreasCard
                  context="onboarding"
                  title={(
                    <span>
                      NYC Neighborhood <span className="text-rose-500">*</span>
                    </span>
                  )}
                  subtitle="Choose your primary neighborhood so we can match local demand."
                  helperText="Pick the main neighborhood you plan to teach in."
                  selectionMode="single"
                  showBulkActions={false}
                  globalNeighborhoodFilter={globalNeighborhoodFilter}
                  onGlobalFilterChange={(value) => {
                    setGlobalNeighborhoodFilter(value);
                    clearError('neighborhood');
                  }}
                  nycBoroughs={NYC_BOROUGHS}
                  boroughNeighborhoods={boroughNeighborhoods}
                  selectedNeighborhoods={selectedNeighborhoods}
                  onToggleNeighborhood={toggleNeighborhood}
                  openBoroughs={openBoroughs}
                  onToggleBoroughAccordion={toggleBoroughAccordion}
                  loadBoroughNeighborhoods={loadBoroughNeighborhoods}
                  toggleBoroughAll={toggleBoroughAll}
                  boroughAccordionRefs={boroughAccordionRefs}
                  idToItem={idToItem}
                  isNYC
                  formatNeighborhoodName={toTitle}
                />
                {errors.neighborhood && (
                  <p className="mt-2 text-sm text-red-600" id="neighborhood-error">
                    {errors.neighborhood}
                  </p>
                )}
              </div>

              <div>
                <BioCard
                  context="dashboard"
                  embedded={false}
                  profile={profile}
                  onProfileChange={(updates) => {
                    setProfile((prev) => ({ ...prev, ...updates }));
                    if (updates.bio !== undefined) clearError('bio');
                    if (updates.years_experience !== undefined) clearError('experienceYears');
                  }}
                  bioTouched={bioTouched}
                  bioTooShort={false}
                  setBioTouched={setBioTouched}
                  onGenerateBio={() => {}}
                  showRewriteButton={false}
                  showMinCharHint={false}
                  showCharCount
                  maxBioChars={500}
                  allowEmptyYears
                  yearsMin={0}
                  yearsMax={70}
                  yearsLabel="Years of Experience (optional)"
                  bioLabel="Brief Bio (optional)"
                />
                {errors.bio && (
                  <p className="mt-2 text-sm text-red-600" id="bio-error">
                    {errors.bio}
                  </p>
                )}
                {errors.experienceYears && (
                  <p className="mt-2 text-sm text-red-600" id="experience-error">
                    {errors.experienceYears}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="flex items-center gap-3 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={hasExistingClients}
                    onChange={(event) => setHasExistingClients(event.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-[#7E22CE] focus:ring-[#7E22CE]"
                  />
                  I have existing clients
                </label>

                <div>
                  <label htmlFor="referral-source" className="block text-sm font-medium text-gray-700">
                    How did you hear about us?
                  </label>
                  <select
                    id="referral-source"
                    value={referralSource}
                    onChange={(event) => setReferralSource(event.target.value)}
                    className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm bg-white text-gray-900 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)]"
                  >
                    <option value="">Select one</option>
                    {REFERRAL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {status === 'error' && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                  Something went wrong. Please try again or email us at teach@instainstru.com
                </div>
              )}

              <button
                type="submit"
                disabled={status === 'loading'}
                className="w-full flex justify-center items-center h-12 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:bg-[#7E22CE] active:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-60 disabled:cursor-not-allowed transform-gpu will-change-transform transition-all"
              >
                {status === 'loading' && (
                  <span className="mr-2 inline-flex h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                )}
                {status === 'loading' ? 'Submitting...' : 'Submit Application'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
    <Script
      id="vtag-ai-js"
      src="https://r2.leadsy.ai/tag.js"
      data-pid="UyudE5UkciQokTPX"
      data-version="062024"
      strategy="afterInteractive"
    />
  </>
  );
}

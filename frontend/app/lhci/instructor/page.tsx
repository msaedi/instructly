// frontend/app/lhci/instructor/page.tsx
// Static instructor profile used by LHCI so the hard gate remains reliable even
// when the backend/API is unavailable in CI. The layout intentionally mimics
// the public instructor page but renders only local, in-memory data (no fetches).

import type { Metadata } from 'next';
import { CalendarDays, Clock, MapPin, Star, Users, Video } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

// eslint-disable-next-line react-refresh/only-export-components
export const metadata: Metadata = {
  title: 'Instructor Profile (LHCI Mock)',
  robots: {
    index: false,
    follow: false,
  },
};

const MOCK_INSTRUCTOR = {
  name: 'Sarah C.',
  instrument: 'Piano & Music Theory',
  tagline: 'Juilliard-trained pianist helping students unlock creative confidence.',
  yearsExperience: 10,
  rating: 4.8,
  reviewCount: 42,
  studentsTaught: 120,
  areaOfService: 'Upper West Side • Online',
  bio: [
    'Sarah combines classical training with modern coaching techniques to keep lessons structured yet playful. Students develop strong technique, ear training, and personalized repertoire plans.',
    'She works with youth and adult learners, offering hybrid lesson plans that mix in-person and online sessions to accommodate busy schedules.',
  ],
};

const MOCK_BADGES = [
  { icon: Video, label: 'Virtual friendly' },
  { icon: CalendarDays, label: 'Flexible scheduling' },
  { icon: Users, label: 'Works with beginners' },
];

const MOCK_SERVICES = [
  {
    id: 'svc-30',
    title: 'Piano Lesson — 30 minutes',
    description: 'Perfect for younger students or focused technique refreshers. Includes personalized warmups and goal tracking.',
    price: '$60',
    durationLabel: '30 min',
    delivery: 'Studio • Virtual',
  },
  {
    id: 'svc-60',
    title: 'Piano Lesson — 60 minutes',
    description: 'Full-length lesson covering repertoire, music theory, and creative exploration tailored to your goals.',
    price: '$100',
    durationLabel: '60 min',
    delivery: 'In-home • Studio • Virtual',
  },
  {
    id: 'svc-ensemble',
    title: 'Duet / Ensemble Coaching',
    description: 'Specialized coaching for duet partners or small ensembles preparing for recitals and auditions.',
    price: '$150',
    durationLabel: '75 min',
    delivery: 'Studio • Virtual',
  },
];

const MOCK_REVIEWS = [
  {
    id: 'rev-1',
    author: 'Allison L.',
    rating: 5,
    headline: 'Patient and encouraging teacher',
    body: 'Sarah helped our daughter master her recital piece with confidence. The practice plans she creates each week keep us on track without feeling overwhelming.',
  },
  {
    id: 'rev-2',
    author: 'James S.',
    rating: 4,
    headline: 'Great for adult learners',
    body: 'As a returning pianist, I appreciate how Sarah balances fundamentals with songs I’m excited to play. The hybrid online/in-person option is a lifesaver.',
  },
];

const MOCK_AVAILABILITY = [
  { day: 'Tuesday', slots: ['4:00 PM', '5:00 PM', '6:30 PM'], location: 'Upper West Side Studio' },
  { day: 'Wednesday', slots: ['12:30 PM', '2:00 PM', '3:30 PM'], location: 'Virtual' },
  { day: 'Saturday', slots: ['10:00 AM', '11:30 AM'], location: 'In-home Manhattan' },
];

export default function LHCIInstructorPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <section className="border-b border-slate-200 bg-gradient-to-br from-slate-100 via-white to-purple-50">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-center sm:gap-10">
          <div className="flex-shrink-0 self-start">
            <Card className="shadow-sm">
              <CardContent className="p-0">
                <Avatar className="h-36 w-36">
                  <AvatarFallback className="text-4xl font-semibold text-purple-600">
                    SC
                  </AvatarFallback>
                </Avatar>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-1 flex-col gap-4">
            <div className="space-y-2">
              <Badge variant="secondary" className="w-fit bg-purple-100 text-purple-700">
                {MOCK_INSTRUCTOR.instrument}
              </Badge>
              <h1 className="text-3xl font-bold text-slate-900" data-testid="lhci-instructor-name">
                {MOCK_INSTRUCTOR.name}
              </h1>
              <p className="max-w-2xl text-base text-slate-700">
                {MOCK_INSTRUCTOR.tagline}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
              <span className="inline-flex items-center gap-1 font-semibold text-slate-900">
                <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" aria-hidden />
                {MOCK_INSTRUCTOR.rating} ({MOCK_INSTRUCTOR.reviewCount} reviews)
              </span>
              <Separator orientation="vertical" className="hidden h-5 sm:block" />
              <span className="inline-flex items-center gap-2">
                <MapPin className="h-4 w-4 text-purple-600" aria-hidden />
                {MOCK_INSTRUCTOR.areaOfService}
              </span>
              <Separator orientation="vertical" className="hidden h-5 sm:block" />
              <span className="inline-flex items-center gap-2">
                <Clock className="h-4 w-4 text-purple-600" aria-hidden />
                {MOCK_INSTRUCTOR.yearsExperience}+ yrs experience
              </span>
            </div>

            <div className="flex flex-wrap gap-3">
              {MOCK_BADGES.map(({ icon: Icon, label }) => (
                <Badge key={label} variant="outline" className="gap-2 border-purple-200 bg-white text-purple-700">
                  <Icon className="h-4 w-4" aria-hidden />
                  {label}
                </Badge>
              ))}
            </div>

            <Button size="lg" className="mt-2 w-fit bg-purple-600 hover:bg-purple-700">
              Check availability
            </Button>
          </div>
        </div>
      </section>

      <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-12">
        <section className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-900">Students coached</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold text-purple-600">
              {MOCK_INSTRUCTOR.studentsTaught}+
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-900">Weekly availability</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold text-purple-600">12 slots</CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-900">Cancellation window</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center gap-2 text-purple-600">
              <Clock className="h-5 w-5" aria-hidden />
              <span className="text-xl font-semibold">24 hours</span>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-6 md:grid-cols-[2fr,1fr]">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="text-xl font-semibold text-slate-900">About the instructor</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-slate-700">
              {MOCK_INSTRUCTOR.bio.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="text-xl font-semibold text-slate-900">Next availability</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-600">
              {MOCK_AVAILABILITY.map(({ day, slots, location }) => (
                <div key={day} className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="flex items-center justify-between text-slate-900">
                    <span className="font-medium">{day}</span>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-purple-600">
                      <Clock className="h-3 w-3" aria-hidden />
                      {slots.length} slots
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-slate-700">
                    {slots.map((slot) => (
                      <span key={slot} className="rounded-full bg-purple-50 px-3 py-1 text-xs font-medium text-purple-700">
                        {slot}
                      </span>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-slate-500">{location}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-semibold text-slate-900">Services & pricing</h2>
            <Badge variant="outline" className="gap-2 text-sm text-slate-700">
              <Clock className="h-4 w-4 text-purple-600" aria-hidden />
              Transparent rates
            </Badge>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {MOCK_SERVICES.map((service) => (
              <Card key={service.id} className="flex flex-col justify-between border-slate-200 shadow-sm">
                <CardHeader className="space-y-2 pb-0">
                  <CardTitle className="text-lg font-semibold text-slate-900">
                    {service.title}
                  </CardTitle>
                  <p className="text-sm text-slate-600">{service.description}</p>
                </CardHeader>
                <CardContent className="mt-4 space-y-3">
                  <div className="flex items-center justify-between text-sm text-slate-700">
                    <span className="font-semibold text-slate-900">{service.price}</span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                      <Clock className="h-3 w-3" aria-hidden />
                      {service.durationLabel}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">{service.delivery}</p>
                  <Button variant="outline" className="w-full border-purple-200 text-purple-700 hover:bg-purple-50">
                    Book trial
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl font-semibold text-slate-900">Student feedback</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {MOCK_REVIEWS.map((review) => (
              <Card key={review.id} className="h-full border-slate-200 shadow-sm">
                <CardHeader className="space-y-2">
                  <CardTitle className="flex items-center justify-between text-base font-semibold text-slate-900">
                    <span>{review.headline}</span>
                    <span className="inline-flex items-center gap-1 text-sm text-purple-700">
                      <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" aria-hidden />
                      {review.rating.toFixed(1)}
                    </span>
                  </CardTitle>
                  <p className="text-xs uppercase tracking-wide text-slate-500">{review.author}</p>
                </CardHeader>
                <CardContent className="text-sm text-slate-700">{review.body}</CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

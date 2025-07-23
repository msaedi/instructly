# Category Implementation
*July 21, 2025 - Service Catalog Category Update*

## 🎯 Category Redesign Overview

We're moving from 8 categories to 7, with a cleaner, service-first approach. Users will select WHAT they want to learn before seeing WHO teaches it.

## 📊 New Category Structure

### Desktop View - All 7 Categories Horizontally

|            |                    |                  |          |                            |                        |             |
|------------|--------------------|--------------------|----------|----------------------------|------------------------|-------------|
| 🎵         | 📚                 | 💪                 | 🗣️       | 🎨                         | 👶                     | ✨          |
| Music      | Tutoring           | Sports & Fitness   | Language | Arts                       | Kids                   | Hidden Gems |
| Instrument Voice Theory | Academic STEM Tech |                    |          | Performing Visual Applied  | Infant Toddler Preteen |             |

## 📝 Category Descriptions

1. **Music** - Instrument instruction, voice/singing lessons, music theory
2. **Tutoring** - Academic subjects, STEM fields, and technology
3. **Sports & Fitness** - Physical activities and fitness training
4. **Language** - All language learning (Spanish, French, ESL, etc.)
5. **Arts** - Performing arts, visual arts, and applied arts (dance, painting, crafts)
6. **Kids** - All services specifically designed for children (ages 0-12)
7. **Hidden Gems** - Unique and specialty services that don't fit elsewhere

## 🔧 Implementation Requirements

### Display Rules
- All 7 categories must be visible in one horizontal row on desktop
- Mobile shows 3.5 categories with horizontal scroll
- Icons are displayed above category names
- Subtitles appear below main titles (no punctuation, single line)
- No text wrapping to additional lines

### Kids Category Special Handling
- Shows services from other categories adapted for children
- Age range: 0-12 years old
- Services should be clearly marked as kid-friendly
- May duplicate services (e.g., "Piano Lessons" and "Piano Lessons for Kids")

### Hidden Gems Category
- Curated selection of unique services
- Not a dumping ground for miscellaneous items
- Should create intrigue and discovery
- Examples: Wine tasting, life coaching, specialty crafts

## 🚨 Critical Notes

1. **Service-First Paradigm** - Homepage must lead with "What do you want to learn?"
2. **No Free Text** - Users can only select from the 47 catalog services
3. **Mobile Priority** - 60% of users, horizontal scroll must be smooth
4. **Clean Break** - No backward compatibility with old 8-category system

## 📋 What We Need From X-Team

1. Update backend to support 7 categories instead of 8
2. Remap all services to new categories
3. Implement horizontal scrolling for mobile
4. Ensure Kids category can pull/filter from other categories
5. Add subtitle support to category display

## ❓ Questions for X-Team

1. Can you provide the complete list of 47 services?
2. How should Kids services be handled in the database?
3. Any technical constraints for horizontal scrolling on mobile?
4. Timeline for backend category remapping?

This redesign is critical for transforming InstaInstru from "browse instructors" to "find services" - the foundation of our platform's success.

## 📋 Complete Service Catalog

### 1. **Music** - Instrument Voice Theory
Piano/Keyboard, Guitar, Voice/Singing, Violin, Drums, Ukulele, Music Theory, Vocal Coaching, Bass Guitar, Saxophone, Musical Theater Voice, Songwriting, Flute, Cello, Music Production/DAW, Trumpet, Clarinet, DJ Skills, Pop Vocals/Rock Vocals, Composition, Jazz Vocals, Viola, Percussion, Trombone, Harmonica, Opera Singing, Choir Singing/Choral Singing, French Horn, Beatboxing, Sound Engineering, Banjo, Double Bass, Mandolin, Accordion, Harp, Music Arrangement

### 2. **Tutoring** - Academic STEM Tech
Math Tutoring Elementary, SAT Prep, Algebra I, Algebra II, Reading Tutoring Elementary, Essay Writing, Calculus AP, ACT Prep, Chemistry, Physics, Coding/Programming, Biology, Homework Help K-5, Python, Geometry, English/Literature, Writing Skills, Pre-Calculus, Computer Science, Statistics AP, Middle School Math, US History, Web Development, AP Sciences, Pre-Algebra, JavaScript, World History, Trigonometry, Study Skills, SHSAT Prep, Microsoft Office, Java, GRE Prep, Data Science, Regents Prep, Digital Marketing Basics, GMAT Prep, Government/Politics, Basic Computer Skills, LSAT Prep, MCAT Prep, Middle School English, Middle School Science, Google Workspace, Graphic Design Software, ISEE/SSAT Prep, Video Editing, Machine Learning, Robotics, Engineering Concepts, Social Media for Business

### 3. **Sports & Fitness**
Personal Training, Yoga, Swimming, Tennis, Basketball Skills, Soccer Skills, Martial Arts, Running/Track, Pilates, Golf, Strength Training, Boxing, Dance Fitness/Zumba, Baseball/Softball, Volleyball, Karate, Stretching/Flexibility, HIIT Training, Cardio Fitness, Barre, Nutrition Coaching, Taekwondo, CrossFit, Football Skills, Meditation/Mindfulness, Ice Skating, Jiu-Jitsu, Rock Climbing, Fencing, Muay Thai, Lacrosse, Skateboarding, Tai Chi, Archery, Rollerblading

### 4. **Language**
Spanish, ESL, French, Mandarin Chinese, Italian, Conversational English, German, Japanese, Sign Language ASL, Korean, Portuguese, Russian, Business English, Arabic, Hebrew, Accent Reduction, TOEFL Prep, Hindi, English Grammar, Public Speaking, Medical Spanish, Legal Spanish, Travel Language Basics

### 5. **Arts** - Performing Visual Applied
Photography, Drawing, Acting, Ballet, Painting Watercolor, Hip Hop Dance, Contemporary Dance, Jazz Dance, Painting Acrylic, Pottery/Ceramics, Digital Art, Sewing, Jewelry Making, Ballroom Dancing, Theater Performance, Illustration, Fashion Design, Painting Oil, Knitting, Latin Dancing, Interior Design Basics, Tap Dance, Portrait Drawing, Calligraphy, Floral Arrangement, Improv Comedy, Sketching, Crocheting, Woodworking, Stand-up Comedy, Embroidery, Graffiti Art, Scrapbooking, Leathercraft, Magic/Illusion, Candle Making, Soap Making

### 6. **Kids** - Infant Toddler Preteen
Swimming for Kids, Piano for Kids, Math Tutoring K-5, Reading Tutoring K-5, Soccer for Kids, Spanish for Kids, Art for Kids, Dance for Kids, Martial Arts for Kids, Basketball for Kids, Guitar for Kids, Homework Help, Kids Yoga, Drama/Theater for Kids, Chess for Kids, Coding for Kids, Gymnastics, French for Kids, Writing Skills for Kids, Violin for Kids Suzuki, Science for Kids, Crafts for Kids, Early Reading Ages 3-5, Kids Choir/Kids Singing, Drums for Kids, Pre-K Prep, Kindergarten Readiness, Mandarin for Kids, Music & Movement Toddlers, Developmental Movement

### 7. **Hidden Gems**
Life Coaching, Cooking Various Cuisines, Wine Tasting/Wine Appreciation, Public Speaking, Makeup Application, Chess, Personal Styling, Career Coaching, Self-Defense, Dog Training, CPR/First Aid, Baking & Pastry, Creative Writing, Meditation/Mindfulness, Home Organization, Etiquette/Manners, Personal Branding, Gardening, Time Management, Cake Decorating, Negotiation Skills, Coffee Barista Skills, Cocktail Making, LinkedIn Optimization, Presentation Skills, Tarot Reading, Massage Techniques, Reiki, Video Production, Poetry, Podcasting, Aromatherapy, NYC History Tours, Screenwriting, Astrology Reading, Urban Farming, Herbalism Basics, Genealogy Research, Game Design, Origami, Model Building, Bird Watching, Beekeeping Basics, Board Game Strategy, Street Art Tours, Subway Navigation, Food Tour Guiding, NYC Real Estate Basics, Collecting Coins/Collecting Stamps

import { API_URL, API_ENDPOINTS } from '@/lib/api';

const instructors = [
    {
      fullName: "Sarah Chen",
      email: "instructor1@example.com",
      categories: ["Yoga", "Meditation"],
      bio: "Certified yoga instructor with 8 years of experience teaching vinyasa and hatha yoga.",
      hourlyRate: 75,
      yearsExperience: 8
    },
    {
      fullName: "Michael Rodriguez",
      email: "instructor2@example.com", 
      categories: ["Piano", "Music Theory"],
      bio: "Classically trained pianist with 15 years of teaching experience. Specializes in jazz and classical piano.",
      hourlyRate: 85,
      yearsExperience: 1
    },
    {
      fullName: "Maria Garcia",
      email: "instructor3@example.com",
      categories: ["Spanish", "ESL"],
      bio: "Native Spanish speaker with a degree in Spanish Literature. Experienced in teaching both beginners and advanced students.",
      hourlyRate: 65,
      yearsExperience: 15
    },
    {
      fullName: "David Thompson",
      email: "instructor4@example.com",
      categories: ["Personal Training", "Nutrition"],
      bio: "Certified personal trainer and nutrition coach. Specializes in strength training and weight loss programs.",
      hourlyRate: 90,
      yearsExperience: 2
    },
    {
      fullName: "Emma Wilson",
      email: "instructor5@example.com",
      categories: ["Photography", "Photo Editing"],
      bio: "Professional photographer with expertise in portrait and street photography. Adobe Certified Expert.",
      hourlyRate: 80,
      yearsExperience: 3
    }
  ];
  
  async function createInstructorAccounts() {
    console.log("Starting to create instructor accounts...");
    
    for (const instructor of instructors) {
      try {
        // Create account
        const registerResponse = await fetch(`${API_URL}${API_ENDPOINTS.REGISTER}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: instructor.fullName,
            email: instructor.email,
            password: "testpass123",
            role: "instructor"
          })
        });
      
        if (!registerResponse.ok) {
          throw new Error(`Failed to create account for ${instructor.email}`);
        }
      
        console.log(`✅ Created account for ${instructor.fullName}`);
      
        // Get auth token for the new instructor
        const loginResponse = await fetch(`${API_URL}${API_ENDPOINTS.LOGIN}`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            username: instructor.email,
            password: "testpass123"
          })
        });
      
        if (!loginResponse.ok) {
          throw new Error(`Failed to login as ${instructor.email}`);
        }
      
        const { access_token } = await loginResponse.json();
        
        // Check if user already exists
        const checkResponse = await fetch(`${API_URL}${API_ENDPOINTS.ME}`, {
          headers: {
            "Authorization": `Bearer ${access_token}`
          }
        });
        
        if (checkResponse.ok) {
          console.log(`ℹ️  ${instructor.fullName} already exists, skipping...`);
          continue;
        }
        
        // Transform categories into services with the same hourly rate
        const services = instructor.categories.map(skill => ({
          skill: skill,
          hourly_rate: instructor.hourlyRate,
          description: `${skill} lessons and training`
        }));
      
        // Create instructor profile with new schema
        const profileResponse = await fetch(`${API_URL}${API_ENDPOINTS.INSTRUCTOR_PROFILE}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${access_token}`
          },
          body: JSON.stringify({
            bio: instructor.bio,
            areas_of_service: ["Manhattan", "Brooklyn", "Queens"],  // Default areas
            years_experience: instructor.yearsExperience,
            services: services  // Array of services with individual pricing
          })
        });
      
        if (!profileResponse.ok) {
          const errorDetail = await profileResponse.text();
          console.error(`Response status: ${profileResponse.status}`);
          console.error(`Error detail: ${errorDetail}`);
          throw new Error(`Failed to create profile for ${instructor.email}`);
        }
      
        console.log(`✅ Created profile for ${instructor.fullName}`);
      
      } catch (error) {
        console.error(`❌ Error for ${instructor.email}:`, error.message);
      }
    }
  
    console.log("Finished creating instructor accounts and profiles!");
  }
  
  // Run the script
  createInstructorAccounts().catch(console.error);
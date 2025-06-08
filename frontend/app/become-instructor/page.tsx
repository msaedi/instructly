"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronLeft, ChevronRight, X, AlertCircle } from "lucide-react";

interface Service {
  skill: string;
  hourly_rate: number;
  description: string;
}

interface FormData {
  services: Service[];
  yearsExperience: number;
  bio: string;
  areasOfService: string[];
}

const SKILLS_OPTIONS = [
  "Yoga", "Meditation", "Piano", "Music Theory", "Spanish", "ESL",
  "Personal Training", "Nutrition", "Photography", "Photo Editing",
  "Programming", "Web Development", "Data Science", "Language Tutoring",
  "Art", "Drawing", "Painting", "Dance", "Fitness", "Cooking"
];

const NYC_AREAS = [
  "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island",
  "Upper East Side", "Upper West Side", "Midtown", "Downtown",
  "Williamsburg", "Astoria", "Long Island City", "Park Slope"
];

export default function BecomeInstructorPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<FormData>({
    services: [],
    yearsExperience: 0,
    bio: "",
    areasOfService: [],
  });
  const [newService, setNewService] = useState<Service>({
    skill: "",
    hourly_rate: 50,
    description: ""
  });
  const [userRole, setUserRole] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSuccess, setShowSuccess] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem("access_token");
      if (!token) {
        router.push("/login?redirect=/become-instructor");
        return;
      }

      try {
        const response = await fetch("http://localhost:8000/auth/me", {
          headers: {
            Authorization: `Bearer ${token}`
          }
        });
        
        if (!response.ok) throw new Error("Failed to fetch user data");
        
        const data = await response.json();
        setUserRole(data.role);
      } catch (error) {
        console.error("Error fetching user data:", error);
        router.push("/login?redirect=/become-instructor");
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, [router]);

  const addService = () => {
    setErrors([]);
    
    if (!newService.skill || !newService.hourly_rate) {
      setErrors(["Please select a skill and set an hourly rate"]);
      return;
    }
    
    if (formData.services.some(s => s.skill === newService.skill)) {
      setErrors(["You've already added this service"]);
      return;
    }

    setFormData(prev => ({
      ...prev,
      services: [...prev.services, newService]
    }));
    
    setNewService({
      skill: "",
      hourly_rate: 50,
      description: ""
    });
  };

  const removeService = (index: number) => {
    setFormData(prev => ({
      ...prev,
      services: prev.services.filter((_, i) => i !== index)
    }));
  };

  const toggleArea = (area: string) => {
    setFormData(prev => ({
      ...prev,
      areasOfService: prev.areasOfService.includes(area)
        ? prev.areasOfService.filter(a => a !== area)
        : [...prev.areasOfService, area]
    }));
  };

  const handleInputChange = (field: keyof FormData, value: string | number) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleNext = async () => {
    setErrors([]);
    
    if (currentStep < 2) {
      if (formData.services.length === 0) {
        setErrors(["Please add at least one service with pricing"]);
        return;
      }
      setCurrentStep(prev => prev + 1);
    } else {
      const validationErrors = [];
      
      if (!formData.bio || formData.bio.length < 10) {
        validationErrors.push("Please provide a bio (at least 10 characters)");
      }
      if (formData.areasOfService.length === 0) {
        validationErrors.push("Please select at least one area of service");
      }
      
      if (validationErrors.length > 0) {
        setErrors(validationErrors);
        return;
      }
  
      try {
        const token = localStorage.getItem("access_token");
        
        const response = await fetch("http://localhost:8000/instructors/profile", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            services: formData.services,
            years_experience: formData.yearsExperience,
            bio: formData.bio,
            areas_of_service: formData.areasOfService
          })
        });
  
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to create instructor profile");
        }
  
        setShowSuccess(true);
        setTimeout(() => {
          router.push("/dashboard/instructor");
        }, 2000);
        
      } catch (error) {
        console.error("Error creating profile:", error);
        setErrors([error instanceof Error ? error.message : "Failed to create profile"]);
      }
    }
  };

  const handlePrevious = () => {
    setCurrentStep(prev => prev - 1);
    setErrors([]);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (userRole === "instructor") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-800 mb-4">
            You're already an instructor!
          </h1>
          <button
            onClick={() => router.push("/dashboard/instructor")}
            className="bg-indigo-500 text-white px-6 py-2 rounded-lg hover:bg-indigo-600 transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (showSuccess) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-white p-8 rounded-lg shadow-lg text-center max-w-md">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check className="h-8 w-8 text-green-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">
            Congratulations!
          </h2>
          <p className="text-gray-600 mb-4">
            You're now an instructor! Redirecting to your dashboard...
          </p>
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-center mb-8">Become an Instructor</h1>
      
      {/* Progress Bar */}
      <div className="mb-8">
        <div className="flex justify-between mb-2">
          <span className="text-sm font-medium text-gray-600">Step {currentStep} of 2</span>
          <span className="text-sm font-medium text-gray-600">
            {currentStep === 1 ? "Services & Experience" : "Profile Details"}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${(currentStep / 2) * 100}%` }}
          ></div>
        </div>
      </div>

      {/* Error Display */}
      {errors.length > 0 && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex">
            <AlertCircle className="h-5 w-5 text-red-400 mr-2" />
            <div>
              <h3 className="text-sm font-medium text-red-800">Please fix the following:</h3>
              <ul className="mt-1 list-disc list-inside text-sm text-red-700">
                {errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Step 1: Services and Experience */}
      {currentStep === 1 && (
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Services & Pricing
            </label>
            
            {/* Add Service Form */}
            <div className="border rounded-lg p-4 mb-4 bg-gray-50">
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Select Skill</label>
                    <select
                      value={newService.skill}
                      onChange={(e) => setNewService({...newService, skill: e.target.value})}
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="">Choose a skill...</option>
                      {SKILLS_OPTIONS.filter(skill => 
                        !formData.services.some(s => s.skill === skill)
                      ).map(skill => (
                        <option key={skill} value={skill}>{skill}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Hourly Rate ($)</label>
                    <input
                      type="number"
                      min="0"
                      value={newService.hourly_rate}
                      onChange={(e) => setNewService({...newService, hourly_rate: parseInt(e.target.value) || 0})}
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Description (optional)</label>
                  <input
                    type="text"
                    placeholder="Brief description of this service..."
                    value={newService.description}
                    onChange={(e) => setNewService({...newService, description: e.target.value})}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                
                <button
                  type="button"
                  onClick={addService}
                  className="w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                >
                  Add Service
                </button>
              </div>
            </div>

            {/* Services List */}
            {formData.services.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-gray-700">Your Services:</h3>
                {formData.services.map((service, index) => (
                  <div key={index} className="flex justify-between items-center p-3 bg-white border rounded-lg">
                    <div>
                      <span className="font-medium">{service.skill}</span>
                      <span className="text-gray-600 ml-2">${service.hourly_rate}/hr</span>
                      {service.description && (
                        <p className="text-sm text-gray-500">{service.description}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => removeService(index)}
                      className="text-red-600 hover:text-red-800"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Years of Experience
            </label>
            <input
              type="number"
              min="0"
              value={formData.yearsExperience}
              onChange={(e) => handleInputChange("yearsExperience", parseInt(e.target.value) || 0)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
      )}

      {/* Step 2: Profile Details */}
      {currentStep === 2 && (
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Bio
            </label>
            <textarea
              value={formData.bio}
              onChange={(e) => handleInputChange("bio", e.target.value)}
              rows={4}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              placeholder="Tell us about your teaching experience and approach..."
            />
            <p className="mt-1 text-sm text-gray-500">
              {formData.bio.length}/10 characters minimum
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Areas of Service (Select all that apply)
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {NYC_AREAS.map((area) => (
                <label
                  key={area}
                  className="flex items-center space-x-2 p-2 border rounded-lg cursor-pointer hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={formData.areasOfService.includes(area)}
                    onChange={() => toggleArea(area)}
                    className="h-4 w-4 text-indigo-500 rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">{area}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        {currentStep > 1 && (
          <button
            onClick={handlePrevious}
            className="flex items-center gap-2 px-6 py-2 border rounded-lg hover:bg-gray-50 transition-colors"
          >
            <ChevronLeft className="h-5 w-5" />
            Previous
          </button>
        )}
        <button
          onClick={handleNext}
          className={`flex items-center gap-2 px-6 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors ${
            currentStep === 1 ? "ml-auto" : ""
          }`}
        >
          {currentStep === 2 ? "Submit" : "Next"}
          {currentStep === 1 && <ChevronRight className="h-5 w-5" />}
        </button>
      </div>
    </div>
  );
}
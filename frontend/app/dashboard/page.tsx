// app/dashboard/page.tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Dashboard() {
  const router = useRouter();

  useEffect(() => {
    const checkUserRoleAndRedirect = async () => {
      const token = localStorage.getItem("access_token");
      
      if (!token) {
        router.push("/login");
        return;
      }

      try {
        const response = await fetch("http://localhost:8000/auth/me", {
          headers: {
            "Authorization": `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          router.push("/login");
          return;
        }

        const userData = await response.json();
        
        // Redirect based on role
        if (userData.role === "instructor") {
          router.push("/dashboard/instructor");
        } else if (userData.role === "student") {
          router.push("/dashboard/student");
        }
      } catch (error) {
        console.error("Error checking user role:", error);
        router.push("/login");
      }
    };

    checkUserRoleAndRedirect();
  }, [router]);

  // Show loading state while checking role
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Loading dashboard...</p>
      </div>
    </div>
  );
}
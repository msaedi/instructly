'use client';

/**
 * Reset Password Page
 *
 * This page handles the password reset process after a user clicks
 * the reset link in their email. It validates the reset token,
 * displays password requirements, and allows users to set a new password.
 * Includes real-time password strength validation and confirmation matching.
 */

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Lock, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import type { PasswordResetConfirm } from '@/types/user';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

interface PasswordValidations { minLength: boolean; hasUppercase: boolean; hasNumber: boolean; }
interface TokenValidationResponse { valid: boolean; email?: string; error?: string; }

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [isVerifying, setIsVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [error, setError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);
  const [passwordValidations, setPasswordValidations] = useState<PasswordValidations>({ minLength: false, hasUppercase: false, hasNumber: false });

  const verifyToken = useCallback(async () => {
    if (!token) { setIsVerifying(false); return; }
    try {
      const response = await fetchAPI(`/api/v1/password-reset/verify/${token}`);
      const data: TokenValidationResponse = await response.json();
      if (data.valid) { setTokenValid(true); }
      else { setError('This reset link is invalid or has expired.'); }
    } catch {
      setError('Failed to verify reset link.');
    } finally { setIsVerifying(false); }
  }, [token]);
  useEffect(() => { void verifyToken(); }, [token, verifyToken]);
  useEffect(() => {
    setPasswordValidations({ minLength: password.length >= 8, hasUppercase: /[A-Z]/.test(password), hasNumber: /[0-9]/.test(password) });
  }, [password]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError('');
    if (password !== confirmPassword) { setError('Passwords do not match'); return; }
    if (!Object.values(passwordValidations).every(Boolean)) { setError('Password does not meet all requirements'); return; }
    setRequestStatus(RequestStatus.LOADING);
    try {
      const resetData: PasswordResetConfirm = { token: token!, new_password: password, password_confirm: confirmPassword };
      const response = await fetchAPI('/api/v1/password-reset/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: resetData.token, new_password: resetData.new_password }) });
      if (!response.ok) { const data = await response.json(); if (response.status === 400 && data.detail?.includes('expired')) { throw new Error('This reset link has expired. Please request a new one.'); } throw new Error(data.detail || 'Failed to reset password'); }
      setRequestStatus(RequestStatus.SUCCESS); setIsSuccess(true);
    } catch (err) { setError(getErrorMessage(err)); setRequestStatus(RequestStatus.ERROR); }
  };

  const handleGoToLogin = () => { router.push('/login'); };
  const isLoading = requestStatus === RequestStatus.LOADING;
  if (isVerifying) return (<div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#7E22CE]" role="status" aria-label="Verifying reset link"></div></div>);
  if (!token || !tokenValid) return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link href="/" className="flex justify-center mb-6"><h1 className="text-4xl font-bold text-[#7E22CE] dark:text-purple-400">{BRAND.name}</h1></Link>
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10 text-center">
          <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 dark:bg-red-900/20 mb-4"><XCircle className="h-6 w-6 text-red-600 dark:text-red-400" aria-hidden="true" /></div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Invalid Reset Link</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">{error || 'This password reset link is invalid or has expired.'}</p>
          <Link href="/forgot-password" className="text-[#7E22CE] hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-300 font-medium">Request a new reset link</Link>
        </div>
      </div>
    </div>
  );
  if (isSuccess) return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link href="/" className="flex justify-center mb-6"><h1 className="text-4xl font-bold text-[#7E22CE] dark:text-purple-400">{BRAND.name}</h1></Link>
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10 text-center">
          <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/20 mb-4"><CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" /></div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Password Reset Successful</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Your password has been successfully reset. You can now log in with your new password.</p>
          <button onClick={handleGoToLogin} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] dark:ring-offset-gray-800">Go to Login</button>
        </div>
      </div>
    </div>
  );
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link href="/" className="flex justify-center mb-6"><h1 className="text-4xl font-bold text-[#7E22CE] dark:text-purple-400">iNSTAiNSTRU</h1></Link>
        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">Reset your password</h2>
      </div>
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">New Password</label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"><Lock className="h-5 w-5 text-gray-400" aria-hidden="true" /></div>
                <input id="password" name="password" type={showPassword ? 'text' : 'password'} required value={password} onChange={(e) => setPassword(e.target.value)} disabled={isLoading} className="appearance-none block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed" placeholder="Enter new password" aria-describedby="password-requirements" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:text-[#7E22CE]"
                  style={{ outline: 'none', boxShadow: 'none' }}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (<EyeOff className="h-5 w-5 text-current" />) : (<Eye className="h-5 w-5 text-current" />)}
                </button>
              </div>
            </div>
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Confirm New Password</label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"><Lock className="h-5 w-5 text-gray-400" aria-hidden="true" /></div>
                <input id="confirmPassword" name="confirmPassword" type={showConfirmPassword ? 'text' : 'password'} required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} disabled={isLoading} className="appearance-none block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed" placeholder="Confirm new password" />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:text-[#7E22CE]"
                  style={{ outline: 'none', boxShadow: 'none' }}
                  aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                >
                  {showConfirmPassword ? (<EyeOff className="h-5 w-5 text-current" />) : (<Eye className="h-5 w-5 text-current" />)}
                </button>
              </div>
            </div>
            <div id="password-requirements" className="rounded-md bg-gray-50 dark:bg-gray-700 p-3">
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Password must contain:</p>
              <ul className="text-xs space-y-1" role="list">
                <li className={`flex items-center ${passwordValidations.minLength ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>{passwordValidations.minLength ? '✓' : '○'} At least 8 characters</li>
                <li className={`flex items-center ${passwordValidations.hasUppercase ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>{passwordValidations.hasUppercase ? '✓' : '○'} One uppercase letter</li>
                <li className={`flex items-center ${passwordValidations.hasNumber ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>{passwordValidations.hasNumber ? '✓' : '○'} One number</li>
              </ul>
            </div>
            {error && (<div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert"><p className="text-sm text-red-800 dark:text-red-400">{error}</p></div>)}
            <div>
              <button type="submit" disabled={isLoading || !Object.values(passwordValidations).every((v) => v)} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed dark:ring-offset-gray-800">{isLoading ? 'Resetting...' : 'Reset Password'}</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#7E22CE]" role="status" aria-label="Loading"></div></div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

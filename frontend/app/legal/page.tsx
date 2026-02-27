'use client';

import { useMemo, useSyncExternalStore, type ReactNode } from 'react';
import Link from 'next/link';
import { BRAND } from '@/app/config/brand';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { RoleName } from '@/types/enums';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { cn } from '@/lib/utils';

type LegalTable = {
  headers: string[];
  rows: string[][];
};

type LegalSection = {
  heading: string;
  body?: ReactNode[];
  list?: ReactNode[];
  bodyAfterList?: ReactNode[];
  table?: LegalTable;
};

type LegalDocument = {
  id: string;
  title: string;
  summary: string;
  updated: string;
  sections: LegalSection[];
};

const LEGAL_DOCUMENTS: LegalDocument[] = [
  {
    id: 'terms',
    title: `${BRAND.name} Terms of Service`,
    summary: `The agreement that governs using the iNSTAiNSTRU platform.`,
    updated: 'November 1, 2025',
    sections: [
      {
        heading: 'Introduction',
        body: [
          'Last Updated: November 1, 2025',
          'These iNSTAiNSTRU Terms of Service (the “Terms of Service” or the “Terms”) constitute a legally binding agreement between the User (defined below) of the Platform (defined below) (“you” or “your”) and iNSTAiNSTRU LLC (together with its Affiliates, “iNSTAiNSTRU,” “we,” “us,” or “our”) governing your use of iNSTAiNSTRU’s websites (including www.instainstru.com) (together, the “Sites”), mobile applications (together, the “Apps”), and related services, information, and communications (collectively referred to herein as the “Platform” or the “iNSTAiNSTRU Platform”).',
          'The use of all personal data you submit to the Platform or which we collect about you is governed by our Global Privacy Policy (“Privacy Policy”).',
          'These Terms, together with the Privacy Policy (which are each incorporated by reference, and referred to collectively herein as the “Agreement”), governs your access to and use of the Platform. The Agreement also includes all other supplemental policies and terms referenced and/or linked to within these Terms or otherwise made available to you, all of which also apply to your use of the Platform and are incorporated into the Agreement by reference.',
          'FOR U.S. USERS, SECTION 24 CONTAINS AN ARBITRATION AGREEMENT. THIS ARBITRATION AGREEMENT, WITH LIMITED EXCEPTION, REQUIRES YOU TO SUBMIT DISPUTES AND CLAIMS YOU HAVE AGAINST iNSTAiNSTRU TO BINDING AND FINAL ARBITRATION ON AN INDIVIDUAL BASIS. PLEASE READ IT CAREFULLY AS IT AFFECTS YOUR LEGAL RIGHTS, INCLUDING, IF APPLICABLE, YOUR RIGHT TO OPT OUT OF ARBITRATION.',
          'BY ACKNOWLEDGING THE TERMS OF SERVICE AND/OR ACCESSING AND USING THE PLATFORM, YOU EXPRESSLY ACKNOWLEDGE AND AGREE THAT YOU HAVE READ AND UNDERSTAND AND AGREE TO BE BOUND BY (WITHOUT LIMITATION OR QUALIFICATION), THE AGREEMENT (INCLUDING, ALL TERMS INCORPORATED HEREIN BY REFERENCE).',
          'IF YOU DO NOT AGREE TO BE BOUND BY THE AGREEMENT AND ABIDE BY ITS TERMS, YOU MAY NOT ACCESS OR USE THE PLATFORM.'
        ]
      },
      {
        heading: `1. The Platform`,
        body: [
          'A. Online Marketplace',
          'The Platform is an online web- and app-based two-sided marketplace which enables connections between Students and Instructors. “Student(s)” are individuals and/or businesses seeking to obtain lessons, classes, or instructional sessions (“Lesson(s)”), and “Instructor(s)” are businesses seeking to perform Lessons for Students. Students and Instructors are referred to herein together as “User(s).”',
          'Instructors are independent business owners, providing services under their own name or business name (and not under iNSTAiNSTRU’s name), using their own tools and supplies. Instructors set their own Lesson rates. iNSTAiNSTRU may charge separate service and/or processing fees to Students and/or Instructors as described in the Fees, Payments & Cancellation Supplemental Terms, and may withhold, net, or offset such fees and permitted adjustments (including dispute reversals, chargebacks, and refunds) from amounts processed through the Platform. Instructors may (a) maintain a clientele without any restrictions from iNSTAiNSTRU; (b) offer and provide their services elsewhere, including through competing platforms; and (c) accept or reject Students and Service Agreements (defined below). Instructors are independent contractors of Students, and Students are therefore clients of Instructors, not iNSTAiNSTRU.',
          'Any reference to an Instructor being licensed or credentialed in some manner, or being “badged,” “reliable,” “elite,” “great value,” “background checked,” or “vetted” (or similar language) indicates only that the Instructor has completed a relevant user account registration process or met certain criteria and does not, and shall not be deemed to, represent anything else. Any such description (i) is intended to be useful information for Students to evaluate when they make their own decisions about the identity and suitability of Instructors whom they select or interact with, or contract with via the Platform; and (ii) is not an endorsement, certification, or guarantee by iNSTAiNSTRU of an Instructor’s skills or qualifications or whether they are licensed, insured, trustworthy, safe, or suitable.',
          'Notwithstanding any feature or service of the Platform that a Student may use to expedite Instructor selection, the Student is responsible for determining the Lesson and selecting or otherwise approving their Instructor and should undertake their own research prior to booking any Lesson to be satisfied that a specific Instructor has the right qualifications.',
          'B. iNSTAiNSTRU’s Role',
          'The Platform is not an employment-agency service or business, and iNSTAiNSTRU is not an employer of any User. Users are not employees, partners, representatives, agents, joint venturers, independent contractors, or franchisees of iNSTAiNSTRU.',
          'Users hereby acknowledge and agree that (a) iNSTAiNSTRU does not (i) perform Lessons nor employ individuals to perform Lessons, (ii) supervise, scope, direct, control, or monitor Instructors’ work (including that iNSTAiNSTRU does not set Instructors’ work locations, work hours, or terms of work), nor provide tools or supplies to, or pay any expenses of, Instructors, or (iii) have any control over the quality, timing, legality, failure to provide, or any other aspect whatsoever of Lessons or Users (or the acts or omissions thereof), nor of the integrity, responsibility, competence, qualifications, communications, or the ratings or reviews provided by Users with respect to each other; and (b) the formation of a Service Agreement will not, under any circumstances, create any responsibility or liability for iNSTAiNSTRU, nor any employment or other relationship between iNSTAiNSTRU and the Users or between the Student and the Instructor. Platform requirements (e.g., keeping communications and payments on-platform, safety, identity verification, fraud prevention, or policy compliance) are administrative and trust-and-safety measures only and do not direct or control how Instructors perform Lessons. Users do not have authority to, and may not act as agent for, nor bind or make any representations on behalf of, iNSTAiNSTRU (including that Instructors may not modify all or any part of the iNSTAiNSTRU fees).',
          'iNSTAiNSTRU is neither responsible nor liable for workers’ compensation or any tax payment or withholding, including but not limited to applicable sales taxes, unemployment or employment insurance, social-security contributions, or other applicable payroll withholdings in connection with a User’s use of the Platform, or personal income tax. The Instructor assumes full and sole responsibility for all required and applicable income-tax and social-contribution withholdings as to the Instructor and all persons engaged by the Instructor in the performance of the Lesson Services. Each User assumes all liability for proper classification of such User’s workers based on applicable legal guidelines.',
          'C. License',
          'Subject to your compliance with the terms of the Agreement (including, without limitation, these Terms and iNSTAiNSTRU’s Acceptable-Use Policy), iNSTAiNSTRU grants you a limited, non-exclusive, non-transferable, and revocable license to (a) access and use the Platform (in the locations and territories where the Platform has a presence), (b) download, access, and use the App on your personal device, solely in furtherance of your use of the Platform, and (c) access and view any content, information, and materials made available on the Platform, in all cases for your personal use and the intended purpose of the Platform. All Users are subject to, and agree to comply with, the Acceptable-Use Policy in their use of the Platform. Users may not copy, download, use, redesign, reconfigure, reverse-engineer, or retransmit the Platform or anything therefrom or thereon (in whole or in part) without iNSTAiNSTRU’s prior written consent. Any rights not granted by iNSTAiNSTRU are expressly reserved.',
          'D. User Representations and Warranties'
        ],
        list: [
          'will comply fully with the terms of the Agreement, including, without limitation, these Terms and the Acceptable Use Policy and other Supplemental Terms;',
          'are at least of the legally required age in the jurisdiction in which you reside and are otherwise capable of entering into binding contracts, or you are a Guardian creating and managing an account for a Minor in accordance with Section 2(F) (Youth Safety);',
          'have the right, authority, and capacity to enter into the Agreement (including that you have the right and authority to act on behalf of, and bind to the Agreement, any company or organization on whose behalf you are entering into the Agreement);',
          'will only request and/or perform (as applicable) Lessons in a country where the Platform has a presence;',
          'will respect the privacy (including, without limitation, private, family and home life), property, and data-protection rights of Users and will not record (whether video or audio or otherwise) any Lesson or any interaction by or with any User and/or iNSTAiNSTRU without obtaining the prior written consent of iNSTAiNSTRU and/or the relevant User, as applicable;',
          'will act professionally and responsibly in your interactions with, and fulfill the commitments you make to, other Users (including by communicating clearly and promptly through the Chat Thread, and being present and/or available at the time you agree upon with other Users);',
          'will not discriminate or harass. You will not discriminate against, deny services to, prefer, or discourage any User on the basis of race, color, religion, national origin, sex, gender identity, sexual orientation, disability, age, or any other status protected by applicable law, and you will comply with civil-rights, public-accommodations, and human-rights laws in all Listings, messages, pricing, and selection decisions. Harassment, sexual misconduct, and hateful conduct are prohibited. iNSTAiNSTRU may remove content or suspend/deactivate accounts for violations.',
          'will reasonably accommodate accessibility needs. Users agree to reasonably accommodate disability-related needs where feasible and lawful, and to engage in a good-faith interactive process consistent with applicable accessibility laws.',
          'will only utilize the third-party PSP (as defined in the Fees, Payments and Cancellation Supplemental Terms) to make or receive payment for Lessons;',
          'will use your legal name and/or legal business name (as per your government-issued identification and registration documents) and an up-to-date photo on your profile;',
          'will comply with all applicable local, state, provincial, national, or international laws in your use of the Platform;',
          'will not use the Platform for the purchase or delivery of alcohol or any other controlled or illegal substances or services; and',
          'will ensure that all communications regarding Lessons (including, without limitation, scoping and payments and any questions relevant to Lessons) remain on the Platform, before, during, and after the Lesson;',
          'Non-Circumvention. To protect platform integrity, Users agree not to circumvent the Platform for the same Instructor–Student pairing to avoid fees for 12 months after the most recent Lesson initiated on the Platform, except where prohibited by law.',
          'will comply with sanctions and export laws. You are not located in, organized under the laws of, or ordinarily resident in any embargoed jurisdiction and are not a sanctioned party. You will not use the Platform in violation of U.S. export, re-export, or sanctions laws (including those administered by OFAC, BIS, and other authorities).',
          'if you are a Guardian creating or managing an account for a Minor, you represent that you have lawful authority to do so, will ensure compliance with Section 2(F) (Youth Safety), and will be present for any in-person Lesson.'
        ]
      },
      {
        heading: '2. Use of the Platform',
        body: [
          'A. Registration',
          'You must register and create an account to access and use the Platform, providing only correct and accurate information (such as, without limitation, your name, business name, mailing address, email address, and/or telephone number). You agree to immediately notify iNSTAiNSTRU (at legal@instainstru.com) of any changes to your account information. If any such change relates to ownership of your telephone numbers, you may notify iNSTAiNSTRU by texting STOP to any text message sent to the retiring phone number. Failure to provide and maintain updated and accurate information may result in your inability to use the Platform and/or iNSTAiNSTRU’s termination of this Agreement with you. iNSTAiNSTRU may restrict anyone from completing registration if iNSTAiNSTRU determines such person may threaten the safety and integrity of the Platform, or if such restriction is necessary to address any other reasonable business concern.',
          'Accounts for Minors. Accounts for individuals under the age of majority may only be created and managed by a parent or legal guardian ("Guardian") on the Minor\'s behalf. Guardian-created accounts must comply with Section 2(F) (Youth Safety), and iNSTAiNSTRU may suspend or remove any account that does not meet these requirements.',
          'B. Account Security',
          'You are fully and solely responsible for (a) maintaining the confidentiality of any log-in, password, and account number provided by or given to you to access the Platform; and (b) all activities that occur under your password or account, even if not authorized by you. iNSTAiNSTRU has no control over any User’s account. You agree to notify iNSTAiNSTRU immediately if you suspect any unauthorized party may be using your Platform password or account or any other breach of security.',
          'C. Instructor Onboarding',
          ' (i) Background Checks. To the extent permitted by applicable law, Instructors may be subject to a review process before they can register on, and during their use of, the Platform, which may include, but is not limited to, identity verification and criminal background checks, using third-party services as appropriate ("Background Check(s)"). If you are an Instructor, to the extent permitted under applicable law, you agree to undergo such Background Checks. iNSTAiNSTRU cannot, and does not, assume any responsibility or liability for the accuracy or reliability of Background Check information, nor for any false or misleading statements made by Users of the Platform. Instructors who offer youth-facing Lessons may be subject to additional screening requirements; see Section 2(F) (Youth Safety).',
          ' (ii) Professional Licensing. iNSTAiNSTRU does not independently verify that Instructors have the necessary expertise, or have obtained any licenses, permits, or registrations required, to perform their Lessons. It may be unlawful to perform certain types of Lessons without a license, permit, and/or registration, and performing same may result in law-enforcement action and/or penalties or fines. Instructors are solely responsible for avoiding such prohibited Lessons. If you have questions about how national, state, provincial, territorial, and/or local laws apply to your Lessons on the Platform, you should first seek appropriate legal guidance. Students are solely responsible for determining if an Instructor has the skills and qualifications necessary to perform the specific Lesson and confirming that the Instructor has obtained all required licenses, permits, or registrations, if any. Students may wish to consult their national, state, provincial, territorial and/or local law requirements to determine whether certain Lessons are required to be performed by a licensed or otherwise registered professional.',
          ' (iii) Insurance. Instructors are solely responsible for obtaining and maintaining any insurance they deem appropriate or that applicable law requires for their Lessons (e.g., general liability, professional liability). iNSTAiNSTRU does not provide insurance and is not responsible for an Instructor’s failure to obtain or maintain coverage.',
          ' (iv) Fair-Chance, Consumer-Reporting, and Re-screening. Where background checks are used, iNSTAiNSTRU and its third-party background-check providers will comply with applicable fair-chance/ban-the-box, anti-discrimination, and consumer-reporting laws (if any) in the relevant jurisdiction. If information from a background check may lead to suspension, removal, or denial, iNSTAiNSTRU (or its provider) will deliver any required notices and provide any required opportunity to respond or dispute the information before taking final action, to the extent required by law. For youth-facing categories, you expressly consent to periodic identity re-verification and re-screening and agree to promptly provide any information reasonably requested to complete such reviews.',
          'D. Service Agreement',
          'The Platform allows Users to offer, search for, and book Lessons. After identifying and selecting an Instructor to perform a Lesson, the Student and the Instructor may communicate via the chat thread in the Platform (the &ldquo;Chat Thread&rdquo;) to understand the scope, schedule, and other details of the Lesson (including, without limitation, any specific hazards, obstacles, or impediments in the Lesson location — whether visible or concealed — that may impact the performance of the Lesson). Once the Lesson is scheduled via the Platform by the Instructor, the Student and Instructor form a legally binding contract for the Lesson, which includes the engagement terms proposed and accepted, and any other contractual terms agreed to by the Student and the Instructor in the Chat Thread for the Lesson (the &ldquo;Service Agreement&rdquo;). The Student and the Instructor each agree to comply with the Service Agreement and the Agreement during the engagement, performance, and completion of a Lesson. Instructors are responsible for exercising their own business judgment in entering into Service Agreements and performing Lessons; and acknowledge that there is a chance for individual profit or loss. iNSTAiNSTRU is not a party to any Service Agreement. The formation of a Service Agreement will not, under any circumstances, create any responsibility or liability for iNSTAiNSTRU.',
          'E. Other Parties',
          'F. Youth Safety',
          'G. Activity Risks; Health Warranty (Non-Medical Advice). Some Lessons may involve physical activity or other inherent risks. Students represent they are fit to participate and will consult a physician as needed. iNSTAiNSTRU is not a healthcare provider and does not provide medical advice. To the fullest extent permitted by law, Students assume the inherent risks of participation, and release Instructors and iNSTAiNSTRU from claims arising solely from such inherent risks.'
        ],
        list: [
          (
            <>
              <strong>(i) Instructor Assistants.</strong> Where approved in advance by the Student in the Chat Thread for the Lesson, Instructors may engage assistants, helpers, subcontractors, or other personnel (&ldquo;Instructor Assistant(s)&rdquo;) to perform all or any part of a Lesson; provided that such Instructor Assistants have registered through the Platform and meet all of the requirements applicable to the Instructor as set out in the Agreement. The Instructor assumes full and sole responsibility for the acts and omissions of all Instructor Assistants used in its performance of Lessons and is fully responsible for: (a) the lawful payment of all compensation, benefits, and expenses for its Instructor Assistants, (b) all required and applicable tax withholdings as to such Instructor Assistants, and (c) ensuring all Instructor Assistants are registered Instructors on the Platform.
            </>
          ),
          (
            <>
              <strong>(ii) Student Agents.</strong> The Student agrees that if they have authorized someone other than the Student to book a Lesson on their behalf or to be present in their stead when the Lesson is performed, the Student is appointing that person as their agent (&ldquo;Student Agent(s)&rdquo;), and the Student is deemed to have granted to the Student Agent the authority to act as their agent in relation to the applicable Lesson. Student Agents may direct or instruct the Instructor&apos;s performance of the Lesson, and the Instructor may follow such direction as if the direction was given by the Student. The Student assumes full and sole responsibility for the acts and omissions of Student Agents.
            </>
          ),
          (
            <>
              <strong>(i) Accounts for Minors.</strong> Where permitted by law, a parent or legal guardian (a &ldquo;Guardian&rdquo;) may create, register, and manage an account on behalf of an individual under the age of majority in the jurisdiction of residence (a &ldquo;Minor&rdquo;) solely to arrange youth-facing Lessons. The Guardian is responsible for the Minor&apos;s use of the Platform and for ensuring compliance with this Agreement.
              <div><strong>(ii) Guardian Presence for In-Person Lessons.</strong> For any in-person Lesson involving a Minor, the Guardian must be physically present at the Lesson location for the duration of the Lesson. Instructors may refuse or discontinue a Lesson if a Guardian is not present.</div>
              <div><strong>(iii) Safe-Conduct Requirements.</strong> Youth Lessons must occur in visible, public, or guardian-observable settings. One-on-one, closed-door sessions are prohibited unless the Guardian is present. Off-platform direct contact (calls, texts, DMs) is prohibited except to coordinate immediate logistics already scoped in the Chat Thread. Violations may result in immediate deactivation and referral to authorities where appropriate.</div>
              <div><strong>(iv) Youth-Facing Categories; Enhanced Screening.</strong> iNSTAiNSTRU may designate categories as youth-facing and, to the extent permitted by law, may require additional screening, identity re-verification, and/or background checks of Instructors who offer such Lessons. iNSTAiNSTRU may limit youth-facing Lessons to vetted Instructors and may suspend or remove users, listings, or categories that do not meet Youth Safety requirements.</div>
              <div><strong>(v) Communications &amp; Reporting.</strong> All pre-Lesson scoping and communications must remain on the Platform. To report a safety concern, use the in-product tools or contact safety@instainstru.com. In an emergency, contact local emergency services.</div>
              <div><strong>(vi) Non-Compliance.</strong> Failure to comply with this Section 2(F) may result in suspension or deactivation under Section 6, in addition to any other remedies available to iNSTAiNSTRU.</div>
            </>
          )
        ]
      },
      {
        heading: '3. Fees, Billing, Invoicing, and Payment; Cancellation',
        body: [
          'The terms relevant to fees (including Instructor Payments and iNSTAiNSTRU’s fees), invoicing, payment (including for Lessons, and any other amounts owed by Users hereunder) and cancellation are set out in the Fees, Payments and Cancellation Supplemental Terms, which apply to your access to and use of the Platform. Unless otherwise expressly stated in this Agreement, all fees (including, without limitation, the Lesson Payment and all iNSTAiNSTRU fees) are non-refundable.',
          'Payments and PSP. Payments are facilitated by our third-party payment service provider (&ldquo;PSP&rdquo;). By using payouts, you agree to the PSP’s terms (including know-your-customer checks, sanctions screening, and information reporting) and you authorize iNSTAiNSTRU and the PSP to hold, offset, net, reverse, or delay payouts for fraud prevention, disputes, chargebacks, refunds, policy violations, negative balances, or as required by law.'
        ]
      },
      {
        heading: '4. Contests and Promotional Codes',
        body: [
          'iNSTAiNSTRU may, from time to time, provide certain optional promotional codes, opportunities, and contests to Users. All such optional promotional opportunities will be run at the sole discretion of iNSTAiNSTRU, will be subject to the terms and conditions governing same, and can be implemented, modified, or removed at any time by iNSTAiNSTRU without advance notification. The liability of iNSTAiNSTRU and Affiliates relevant to such promotional opportunities and contests shall be subject to the limitations set forth in Section 13 of these Terms.'
        ]
      },
      {
        heading: '5. Public Areas',
        body: [
          'The Platform may contain profiles, email systems, blogs, message boards, reviews, ratings, lesson postings, chat areas, news groups, forums, communities and/or other message or communication facilities (“Public Areas”) that allow Users to communicate with other Users. You may only use such community areas to send and receive messages and materials that are relevant and proper to the applicable forum.',
          'You understand that all submissions made to Public Areas will be public, and you will be publicly identified by your name or login identification when communicating in Public Areas. iNSTAiNSTRU will not be responsible for the actions of any Users with respect to any information or materials posted or disclosed in Public Areas.'
        ]
      },
      {
        heading: '6. Deactivation and Suspension',
        body: [
          'In the event of an actual or suspected breach by you of any part of the Agreement (including, without limitation, abuse, fraud, or interference with the proper working of the Platform), iNSTAiNSTRU may (a) suspend your right to use the Platform pending its investigation; and/or (b) deactivate your account or limit your use of the Platform upon its confirmation of a breach. iNSTAiNSTRU will provide you with written notice of its determination in accordance with, and as required by, applicable laws. If you wish to appeal any determination made by iNSTAiNSTRU pursuant to this Section, please contact us at support@instainstru.com within 14 days of receipt of such notice with the grounds for your appeal.',
          'If iNSTAiNSTRU suspends or deactivates your account or limits your use of the Platform pursuant to this Section 6, you may not register and/or create a new account under different usernames, identities or contact details (whether under your or any other name or business name), even if you are acting on behalf of a third party.'
        ]
      },
      {
        heading: '7. Termination',
        body: [
          'You may terminate the Agreement between you and iNSTAiNSTRU at any time by ceasing all use of the Platform and deactivating your account. iNSTAiNSTRU may terminate the Agreement between you and iNSTAiNSTRU at any time, and cease providing access to the Platform (pursuant to Section 6 above), if you breach any part of the Agreement or violate applicable laws.',
          'Even after your right to use the Platform is suspended, terminated or limited, the Agreement will remain enforceable against you. iNSTAiNSTRU reserves the right to take appropriate legal action pursuant to the Agreement.'
        ]
      },
      {
        heading: '8. User Generated Content; Feedback',
        body: [
          'A. User Generated Content',
          '“User Generated Content” is defined as any information, content and materials (including any videotape, film, recording, photograph, voice) you provide to iNSTAiNSTRU, its agents, Affiliates, and corporate partners, or other Users in connection with your registration for and use of the Platform (including, without limitation, the information and materials posted or transmitted for use in Public Areas).',
          'User Generated Content is not the opinion of, and has not been verified or approved by, iNSTAiNSTRU. You acknowledge and agree that iNSTAiNSTRU: (a) is not involved in the creation or development of User Generated Content and does not control any User Generated Content; (b) is not responsible or liable for any User Generated Content (including any accuracy, or results obtained by the use thereof or reliance thereon); (c) may, but has no obligation to, monitor or review User Generated Content; and (d) reserves the right to limit or remove User Generated Content if it is not compliant with the terms of the Agreement.',
          'You are and remain solely responsible and liable for your User Generated Content. To the extent permitted by law, you hereby grant iNSTAiNSTRU, for the full duration of all rights that may exist in the User Generated Content (including any legal extensions thereof), a non-exclusive, worldwide, perpetual, irrevocable, royalty-free, fully-paid, unrestricted, sublicensable (through multiple tiers), transferable right and license to publish, reproduce, disseminate, transmit, distribute, modify, adapt, publish, translate, create derivative works from, publicly perform, exhibit, display (in whole or in part), act on and/or otherwise use your User Generated Content, in any media, form or technology now known or later developed, including (without limitation) in connection with any advertising, marketing, and/or publicizing of the Platform, without any approval by, or compensation to, you. Notwithstanding the foregoing, (i) iNSTAiNSTRU will not use your Likeness in paid advertisements (including paid social or display) without either platform-wide notice and a reasonable opt-out mechanism or your express consent, and (ii) the marketing license is revocable for future marketing uses upon 30 days’ written notice (revocation does not affect prior uses or platform-functional uses such as your profile, listings, or reviews). You acknowledge and agree that the foregoing license shall also extend to, and iNSTAiNSTRU and its Affiliates may use (in accordance with this Section), your name, username, image, silhouette and other reproductions of your physical likeness, voice, likeness, screenname(s) and/or any biographical, professional and/or other identifying information (collectively, “Likeness”) in, and in connection with, your use of the Platform, including on websites, social media platforms and third-party digital platforms owned or controlled by us or our Affiliates.',
          'You hereby represent and warrant to iNSTAiNSTRU that (i) you have the lawful authority to grant the rights in your User Generated Content as set out herein, and that such rights do not negatively impact any third-party rights; and (ii) your User Generated Content will not: (1) be false, inaccurate, incomplete or misleading; (2) be fraudulent or involve the transfer or sale of illegal, counterfeit or stolen items; (3) infringe on any third party’s privacy, or copyright, patent, trademark, trade secret or other proprietary or intellectual property right or rights of publicity or personality (to the extent recognized by law in the country where the Lesson is performed); (4) violate any law, statute, ordinance, code, or regulation (including without limitation those governing export control, consumer protection, unfair competition, anti-discrimination, incitement of hatred or false or misleading advertising, anti-spam or privacy); (5) be defamatory, libelous, malicious, threatening, or harassing; (6) be obscene or contain pornography (including but not limited to child pornography) or be harmful to minors; (7) contain any viruses, scripts such as Trojan Horses, SQL injections, worms, time bombs, corrupt files, cancelbots or other computer programming routines that are intended to damage, detrimentally interfere with, surreptitiously intercept or expropriate any system, data or personal information; (8) claim or suggest in any way that you are employed or directly engaged by or affiliated with iNSTAiNSTRU or otherwise purport to act as a representative or agent of iNSTAiNSTRU; or (9) create liability for iNSTAiNSTRU or cause iNSTAiNSTRU to lose (in whole or in part) the services of its Internet Service Providers (ISPs) or other partners or suppliers.',
          'You hereby waive (x) any “moral rights” associated with the User Generated Content (to the extent allowable by law); and (y) all claims relevant to the User Generated Content and iNSTAiNSTRU’s use thereof and of your Likeness. You release the iNSTAiNSTRU Parties (defined below) from, and shall hold such parties harmless from and against, any and all Liabilities (including, without limitation, for defamation, malicious falsehood, invasion of right to privacy, data protection, publicity or personality or any similar matter), based upon or relating to iNSTAiNSTRU’s use and exploitation of such User Generated Content and your Likeness as permitted herein.',
          'iNSTAiNSTRU is entitled to identify a User to other Users or to third parties who claim that their rights have been infringed by User Generated Content submitted by that User, so that they may attempt to resolve the claim directly. If you believe, in good faith, that any User Generated Content provided on or in connection with the Platform is objectionable or infringes any of its rights or the rights of others, you are encouraged to notify iNSTAiNSTRU at support@instainstru.com. If a User discovers that User Generated Content promotes crimes against humanity, incites hatred and/or violence, or concerns child pornography, the User must notify iNSTAiNSTRU at support@instainstru.com.',
          'B. Feedback',
          'The Platform hosts User Generated Content relating to reviews and ratings of specific Instructors (“Feedback”), which enables Users to post and read other Users’ expressions of their experiences. Feedback is the opinion of the User who has posted it. Feedback is not the opinion of, and has not been verified or approved by, iNSTAiNSTRU. iNSTAiNSTRU does not evaluate Users. iNSTAiNSTRU may, but is not obligated to, investigate, modify and/or remove any Feedback or other remarks posted by Users. You may request removal of a review that violates the Agreement or the iNSTAiNSTRU Ratings and Reviews Guidelines by contacting us at support@instainstru.com.'
        ]
      },
      {
        heading: '9. Intellectual Property Rights',
        body: [
          'The Platform, and all components thereof and content made available and/or displayed thereon (including the Marks (defined below), and all text, graphics, editorial content, data, formatting, graphs, designs, HTML, look and feel, photographs, music, sounds, images, software, videos, typefaces, information, tools, designs, interfaces and other content (including the coordination, selection, arrangement, and enhancement of, and any and all intellectual property rights in and to, the foregoing (collectively “Proprietary Material”)), is owned by iNSTAiNSTRU, excluding User Generated Content and any third-party websites made available on or via the Platform. Proprietary Material is protected, in all forms, media and technologies now known or hereinafter developed, by domestic and international laws, including those governing copyright, patents, and other proprietary and intellectual property rights. Any use of the Proprietary Material other than as permitted in the Agreement is expressly prohibited.',
          'The service marks, logos and trademarks of iNSTAiNSTRU (the “Marks”), including without limitation those for iNSTAiNSTRU, are owned by iNSTAiNSTRU. The Marks are not available for use by Instructors. You may not copy or use the Marks without obtaining iNSTAiNSTRU’s express prior written consent. Any other trademarks, service marks, logos and/or trade names appearing on the Platform are the property of their respective owner and may not be used without the prior written consent of such owner.'
        ]
      },
      {
        heading: '10. Links to Third-Party Websites',
        body: [
          'The Platform may contain links (such as, without limitation, hyperlinks, external websites that are framed by the Platform, and advertisements displayed in connection therewith (including as may be featured in any banner or other advertising)) to third-party websites, which are maintained by parties over which iNSTAiNSTRU exercises no control.',
          'Such links are provided for reference and convenience only and do not constitute iNSTAiNSTRU’s endorsement, warranty, or guarantee of, or association with, those websites, their content, or their operators. It is your responsibility to evaluate the content and usefulness of the information obtained from other websites. The use of any website controlled, owned, or operated by a third party is governed by the terms and conditions of use and privacy policy for that website. You access and use such third-party websites at your own risk.',
          'iNSTAiNSTRU has no obligation to monitor, review, limit, or remove links to third-party websites, and is not responsible or liable for any content, advertising, products, services, or other materials on or available from such third-party websites, or for any damage of any kind incurred as a result of your access or use of such websites.',
          'You agree that you will not use any third-party website in connection with any Lesson, or to obtain any lesson-related services, except as expressly permitted by iNSTAiNSTRU.'
        ]
      },
      {
        heading: '11. Copyright Complaints and Copyright Agent',
        body: [
          'If you believe, in good faith, that any materials provided on or in connection with the Platform infringe upon your copyright or other intellectual property right, please send the following information to iNSTAiNSTRU’s Copyright Agent identified below:',
          'A description of the copyrighted work that you claim has been infringed, including the URL (Internet address) or other specific location on the Platform where the material you claim is infringed is visible. Include enough information to allow iNSTAiNSTRU to locate the material, and explain why you think an infringement has taken place;',
          'A description of the location where the original or an authorized copy of the copyrighted work exists — for example, the URL (Internet address) where it is posted or the name of the book in which it has been published;',
          'Your name, address, telephone number, and email address;',
          'A statement by you that you have a good faith belief that the disputed use is not authorized by the copyright owner, its agent, or the law;',
          'A statement by you, made under penalty of perjury, that the information in your notice is accurate and that you are the copyright owner or authorized to act on behalf of the owner of the copyright interest; and',
          'Your electronic or physical signature as the owner of the copyright or the person authorized to act on behalf of the owner of the copyright interest.',
          'The above information must be submitted to iNSTAiNSTRU’s DMCA Agent using the following contact information:',
          'Attn: DMCA Notice',
          'Email: support@instainstru.com',
          'Under United States federal law, if you knowingly misrepresent that online material is infringing, you may be subject to criminal prosecution for perjury and civil penalties, including monetary damages, court costs, and attorneys’ fees.',
          'Please note that the procedure outlined herein is exclusively for notifying iNSTAiNSTRU and its Affiliates that your copyrighted material has been infringed. The preceding requirements are intended to comply with iNSTAiNSTRU’s rights and obligations under the Digital Millennium Copyright Act of 1998 (as it may be amended, "DMCA"), including 17 U.S.C. §512(c), but do not constitute legal advice. It may be advisable to contact an attorney regarding your rights and obligations under the DMCA and other applicable law.',
          'In accordance with the DMCA and other applicable law, we have adopted a policy of terminating, in appropriate circumstances, Users who are deemed to be repeat infringers. We may also, at our sole discretion, limit access to the Platform and/or terminate the User accounts of any Users who infringe any intellectual property rights of others, whether or not there is any repeat infringement.'
        ]
      },
      {
        heading: '12. Disclaimer of Warranties',
        body: [
          'Use of the Platform Is Entirely at Your Own Risk',
          'THE PLATFORM AND THE TECHNOLOGY UNDERLYING IT ARE PROVIDED ON AN “AS IS” AND “AS AVAILABLE” BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED (INCLUDING, BUT NOT LIMITED TO, WARRANTIES OR CONDITIONS OF MERCHANTABILITY, QUALITY OR FITNESS FOR A PARTICULAR PURPOSE, GOOD AND WORKMANLIKE SERVICES, COMPLIANCE WITH ANY LAW, STATUTE, ORDINANCE, REGULATION OR CODE, AND/OR NON-INFRINGEMENT), AND THE SAME ARE EXPRESSLY EXCLUDED.',
          'WITHOUT LIMITING THE FOREGOING, iNSTAiNSTRU AND ITS PARENTS, AFFILIATES, LICENSORS, AND THEIR RESPECTIVE DIRECTORS, OFFICERS, SHAREHOLDERS, AGENTS, INVESTORS, SUBSIDIARIES, ATTORNEYS, REPRESENTATIVES, INSURERS, EMPLOYEES, SUCCESSORS AND ASSIGNS (COLLECTIVELY, THE “AFFILIATES,” AND TOGETHER WITH iNSTAiNSTRU, THE “iNSTAiNSTRU PARTIES”): United States federal law and some states, provinces, and other jurisdictions do not allow the exclusion of and/or limitations on certain implied warranties, so the above exclusions and/or limitations may not apply to you. These terms give you specific legal rights, and you may also have other rights, which vary from jurisdiction to jurisdiction. The disclaimers, exclusions, and limitations under these terms will not apply to the extent prohibited by applicable law.'
        ],
        list: [
          'MAKE NO, AND EXPRESSLY DISCLAIM (TO THE EXTENT PERMITTED BY LAW), ALL REPRESENTATIONS AND WARRANTIES AS TO: (I) THE TIMELINESS, SUITABILITY, ACCURACY, RELIABILITY, COMPLETENESS OR CONTENT OF THE PLATFORM; (II) THE RESULTS THAT MAY BE OBTAINED FROM THE USE OF THE PLATFORM OR ANY LESSON OR SERVICE PROVIDED ON, THROUGH OR IN CONNECTION WITH ITS USE; OR (III) THE LESSONS OR SERVICES PROVIDED BY, OR THE INTERACTIONS OR COMMUNICATIONS OF OR BETWEEN, USERS OF THE PLATFORM (WHETHER ON- OR OFF-LINE, OR OTHERWISE) (INCLUDING, BUT NOT LIMITED TO, ANY INSTRUCTOR’S ABILITY, PROFESSIONAL ACCREDITATION, REGISTRATION OR LICENSURE);',
          'DO NOT WARRANT THAT THE PLATFORM IS OR WILL BE (1) ERROR-FREE OR THAT ACCESS THERETO WILL BE UNINTERRUPTED; OR (2) FREE FROM COMPUTER VIRUSES, SYSTEM FAILURES, WORMS, TROJAN HORSES, OR OTHER HARMFUL COMPONENTS OR MALFUNCTIONS, INCLUDING DURING HYPERLINK TO OR FROM THIRD-PARTY WEBSITES; AND',
          'DO NOT WARRANT, ENDORSE, GUARANTEE, RECOMMEND, OR ASSUME RESPONSIBILITY FOR ANY PRODUCT OR SERVICE ADVERTISED OR OFFERED BY ANY THIRD PARTY THROUGH THE SERVICE OR ANY HYPERLINKED WEBSITE OR SERVICE, INCLUDING BY ANY INSTRUCTOR, AND iNSTAiNSTRU WILL NOT BE A PARTY TO OR IN ANY WAY MONITOR ANY TRANSACTION BETWEEN YOU AND THIRD-PARTY PROVIDERS OF PRODUCTS OR SERVICES.'
        ]
      },
      {
        heading: '13. Limitation of Liability',
        body: [
          'You acknowledge and agree that iNSTAiNSTRU is only willing to provide the Platform if you agree to certain limitations of our liability to you and third parties, as set out in this Section and elsewhere in the Agreement.',
          'THEREFORE, YOU ACKNOWLEDGE AND AGREE THAT, TO THE EXTENT PERMITTED BY APPLICABLE LAW, UNDER NO CIRCUMSTANCES WILL THE iNSTAiNSTRU PARTIES OR THEIR CORPORATE PARTNERS BE RESPONSIBLE OR LIABLE (WHETHER IN CONTRACT, WARRANTY, TORT OR OTHERWISE) FOR, AND SUCH PARTIES EXPRESSLY DISCLAIM, ANY AND ALL LIABILITY, CLAIMS, DEMANDS, DAMAGES (WHETHER DIRECT, INDIRECT, INCIDENTAL, ACTUAL, CONSEQUENTIAL, ECONOMIC, SPECIAL OR EXEMPLARY (INCLUDING, BUT NOT LIMITED TO, LOST PROFITS, LOSS OF DATA OR GOODWILL, SERVICE INTERRUPTION, COMPUTER DAMAGE, SYSTEM FAILURE, FAILURE TO STORE ANY INFORMATION AND THE COST OF SUBSTITUTE PRODUCTS OR SERVICES), EXPENSES (INCLUDING ATTORNEYS’ FEES AND COSTS), LOSSES, GOVERNMENTAL OBLIGATIONS, SUITS, AND/OR CONTROVERSIES OF EVERY KIND AND NATURE, KNOWN AND UNKNOWN, SUSPECTED AND UNSUSPECTED, DISCLOSED AND UNDISCLOSED (COLLECTIVELY, “LIABILITIES”) ARISING OUT OF OR IN ANY WAY RELATED TO OR CONNECTED WITH THE PLATFORM OR YOUR OR ANY OTHER PARTY’S USE OF OR INABILITY TO USE THE PLATFORM, EVEN IF ADVISED OF THE POSSIBILITY OF THE SAME. TO THE EXTENT PERMITTED BY LAW, YOU HEREBY RELEASE THE iNSTAiNSTRU PARTIES AND THEIR CORPORATE PARTNERS FROM THE FOREGOING.',
          'Nothing in the Agreement excludes or limits any liability or warranty that, by applicable law, may not be limited or excluded. Additionally, some jurisdictions do not allow the exclusion of certain warranties or limitation of incidental or consequential damages; in such cases the above limitations may not apply to you in their entirety.',
          'IF, NOTWITHSTANDING THE FOREGOING EXCLUSIONS, IT IS DETERMINED THAT THE iNSTAiNSTRU PARTIES OR THEIR CORPORATE PARTNERS ARE LIABLE FOR DAMAGES, IN NO EVENT WILL THE AGGREGATE LIABILITY, WHETHER ARISING IN CONTRACT, TORT, STRICT LIABILITY OR OTHERWISE, EXCEED: (A) IF YOU ARE A STUDENT, THE TOTAL FEES PAID BY YOU TO iNSTAiNSTRU IN THE SIX (6) MONTHS PRIOR TO THE TIME SUCH CLAIM AROSE; AND (B) IF YOU ARE AN INSTRUCTOR, THE TOTAL LESSON PAYMENTS PAID TO YOU BY STUDENTS IN THE SIX (6) MONTHS PRIOR TO THE TIME SUCH CLAIM AROSE, TO THE EXTENT PERMITTED BY APPLICABLE LAW.',
          'Notwithstanding the foregoing:'
        ],
        list: [
          'For Residents Outside the United States: Nothing in these Terms excludes or limits iNSTAiNSTRU’s liability for (a) death or personal injury caused by iNSTAiNSTRU; or (b) gross negligence or willful misconduct.',
          'For Residents of Germany only: Notwithstanding anything to the contrary in this Section, iNSTAiNSTRU is liable only for breach caused by willful misconduct or gross negligence of its cardinal, material contractual obligations. In the event of initial impossibility, iNSTAiNSTRU may be liable only if it was aware of the impediment to performance prior to entering the Agreement, was unwilling due to gross negligence to remedy that impediment, and a cardinal obligation was breached as a result of that initial impossibility.'
        ]
      },
      {
        heading: '14. Indemnification',
        body: [
          'Users’ indemnification obligations are set out below in this Section. iNSTAiNSTRU reserves the right, in its sole discretion, to assume the exclusive defense and control of any matter otherwise subject to your indemnification. You will not settle any claim or matter without the prior written consent of iNSTAiNSTRU.',
          'Student Indemnification: If you are a Student, you shall indemnify, defend, and hold harmless iNSTAiNSTRU and its Affiliates from and against any and all Liabilities incurred in connection with (i) your use of, inability to use, or participation on the Platform; (ii) your breach or violation of the Agreement; (iii) your violation of any law or the rights of any User or third party; (iv) your use of any third-party links or websites that appear on the Platform; (v) any User Generated Content and/or Feedback submitted by you or using your account on the Platform, including to the extent such content may infringe the intellectual-property rights of a third party or otherwise be illegal or unlawful; and (vi) the acts or omissions of any Student Agents.',
          'Instructor Indemnification: If you are an Instructor, you shall indemnify, defend, and hold harmless iNSTAiNSTRU and its Affiliates from and against any and all Liabilities incurred in connection with (i) your use of, inability to use, or participation on the Platform; (ii) your participation in Lessons or your ability or inability to perform Lessons or receive payment therefor; (iii) your breach or violation of the Agreement; (iv) your violation of any law or the rights of any User or third party; (v) any User Generated Content and/or Feedback submitted by or about you or using your account on the Platform, including to the extent such content may infringe the intellectual-property rights of a third party or otherwise be illegal or unlawful; and (vi) the acts or omissions of any Instructor Assistants.'
        ]
      },
      {
        heading: '15. Dispute Resolution',
        body: [
          'To expedite resolution and reduce the cost of any dispute, controversy, or claim related to, arising from, or regarding your use of the Platform, your relationship with iNSTAiNSTRU, Lessons, or this Agreement (including previous versions) (“Dispute”), you may first attempt to find an amicable solution with iNSTAiNSTRU before initiating any out-of-court settlement (such as mediation or arbitration) or court proceeding (except as may be set forth in Section 24).',
          'Such informal negotiations will commence upon written notice. Your address for such notices is the one associated with your account, with an email copy sent to the email address you have provided to iNSTAiNSTRU. iNSTAiNSTRU’s address for such notice is support@instainstru.com.'
        ]
      },
      {
        heading: '16. App Store–Sourced Apps',
        body: [
          'If you access or download any App from the Apple App Store, you agree to Apple’s Licensed Application End User License Agreement and will comply therewith in your access to and use of the App(s).',
          'If you access or download any App from the Google Play Store, you agree to Google Play Terms of Service and will comply therewith in your access to and use of the App(s).'
        ]
      },
      {
        heading: '17. Changes to the Agreement, the Platform, and the App',
        body: [
          'A. Changes to the Agreement',
          'iNSTAiNSTRU reserves the right, for justifiable and proportionate reasons, at any time, to review, change, modify, update, add to, supplement, suspend, discontinue, or delete any term(s) or provision(s) of this Agreement (including the Terms of Service, Privacy Policy, and/or Acceptable Use Policy).',
          'Notice of such amendments may be given by posting such updates or modifications (or notice thereof) on the Platform, on the relevant online location of the applicable terms or policies, by email, or in any other reasonable manner; such amendments will be effective upon posting. Your continued use of the Platform after such posting constitutes your consent to be bound by the Agreement, as amended.',
          'If modifications and/or updates are material, you will be informed in advance (in the manner set out in this Section) for your acceptance or rejection. If any changes to the Agreement are unacceptable to you or cause you to no longer be in compliance with the Agreement, the previous Terms will apply to your current Lessons, but you will not be able to use the Platform or contract new Lessons and must deactivate your account and immediately stop using the Platform.',
          'After notification of any material changes, your continued use of the Platform following any revision to the Agreement constitutes your complete and irrevocable acceptance of all such changes, except where prohibited by applicable law.',
          'To the extent permitted by law, iNSTAiNSTRU shall not be liable to you for any modification to all or any portion of the Agreement.',
          'B. Changes to the Platform',
          'iNSTAiNSTRU reserves the right, at any time, to review, improve, modify, update, upgrade, discontinue, impose limits, or restrict access to, whether temporarily or permanently, all or any portion of the Platform (including any content or information available on or through the Platform), effective with prior notice (where possible) and without any liability to iNSTAiNSTRU.',
          'To the extent permitted by law, iNSTAiNSTRU shall not be liable to you for any updates, upgrades, modifications to, or discontinuance of, all or any portion of the Platform.',
          'C. Mobile App Updates and Upgrades',
          'By installing the App(s), you consent to the installation of the App(s) and any updates or upgrades that are released through the Platform. The App (including any updates or upgrades) may: (i) cause your device to automatically communicate with iNSTAiNSTRU’s servers to deliver functionality and record usage metrics; (ii) affect App-related preferences or data stored on your device; and/or (iii) collect personal information as described in our Privacy Policy.',
          'You can uninstall the App(s) at any time.'
        ]
      },
      {
        heading: '18. No Rights of Third Parties',
        body: [
          'Except as expressly set out herein or as otherwise required by applicable law, this Agreement is for the sole benefit of iNSTAiNSTRU and the User, and their permitted successors and assigns, and there are no other third-party beneficiaries under the Agreement.',
          'None of the terms of the Agreement are enforceable by any persons who are not a party to it; provided, however, that iNSTAiNSTRU may enforce any such provisions on behalf of its Affiliates.'
        ]
      },
      {
        heading: '19. Notices and Consent to Receive Notices Electronically',
        body: [
          'Unless otherwise specified in the Agreement, all agreements, notices, disclosures, and other communications (collectively, “Notices”) under the Agreement will be in writing and will be deemed to have been duly given:',
          'when received, if personally delivered or sent by certified or registered mail, return receipt requested;',
          'when receipt is electronically confirmed, if transmitted by email; or',
          'on the day it is shown as delivered by the overnight delivery service’s tracking information, if sent for next-day delivery by a recognized overnight delivery service.',
          'Notwithstanding the foregoing, any Notices to which the Agreement refers may be sent to you electronically (including, without limitation, by email or by posting Notices on the Platform), and you consent to receive Notices in this manner. All notices that we provide to you electronically satisfy any legal requirement that such communications be in writing.',
          'If you have any questions about these Terms of Service or about the Platform, please contact us at support@instainstru.com.'
        ]
      },
      {
        heading: '20. Consent to Electronic Signatures',
        body: [
          'By using the Platform, you agree: (a) to transact electronically through the Platform; (b) that your electronic signature is the legal equivalent of your manual signature and has the same legal effect, validity, and enforceability as a paper-based signature; (c) that your use of a keypad, mouse, or other device to select an item, button, icon, or similar act/action constitutes your signature as if actually signed by you in writing; and (d) that no certification authority or third-party verification is necessary to validate your electronic signature, and the lack thereof will not affect its enforceability.'
        ]
      },
      {
        heading: '21. Governing Law',
        body: [
          'Except for Sections 15 (Dispute Resolution) and/or 24 (Jurisdiction-Specific Provisions) hereof, the Agreement and your use of the Platform will be governed by, and construed under, the laws as set out in this Section (without regard to choice of law principles):',
          'For Users within the United States: The laws of the State of New York.',
          'For Users outside of the United States: The laws of England and Wales, and any dispute regarding the Agreement or use of the Platform will only be dealt with by the English courts.',
          'The choices of law set out in this Section shall apply unless and to the extent that federal, state, provincial, local, or international laws, rules, regulations, directives, judgments, or orders binding on or applicable to you or your performance hereunder require that the Agreement or your use of the Platform be governed by the laws of the country in which the Lesson is performed.',
          'This provision is intended only to designate the governing laws to interpret the Agreement and is not intended to create any substantive right for non-residents of the designated jurisdiction to assert claims under such law. Nothing shall prevent iNSTAiNSTRU from bringing proceedings to protect its intellectual property rights before any competent court.'
        ]
      },
      {
        heading: '22. Notices',
        body: [
          'The iNSTAiNSTRU Platform, websites, and apps are owned and operated by iNSTAiNSTRU LLC, a company registered in the State of New York, United States.',
          'If you have any questions about the Agreement or the Platform, please contact us at: support@instainstru.com.'
        ]
      },
      {
        heading: '23. General Provisions',
        body: [
          'a. Relationship of the Parties',
          'No agency, partnership, joint venture, employer-employee or franchiser-franchisee relationship exists, is intended, or is created between you and iNSTAiNSTRU by this Agreement or by your use of the Platform. Users do not have authority to act as an agent for, nor to bind or make any representations on behalf of, iNSTAiNSTRU.',
          'b. Entire Agreement',
          'The Agreement (including any terms linked to in, and incorporated by reference into, these Terms) constitutes the complete and exclusive agreement between you and iNSTAiNSTRU with respect to your use of the Platform, and supersedes any and all prior or contemporaneous agreements, proposals, or communications, except as otherwise specified in the Arbitration Agreement in Section 24(A).',
          'However, the Agreement does not supersede other agreements about different subject matter that you may have with iNSTAiNSTRU (such as any applicable supplemental service terms).',
          'The provisions of the Agreement are intended to be interpreted in a manner that makes them valid, legal, and enforceable.',
          'c. Severability; Waiver',
          'Except for the “Agreement Prohibiting Class Actions and Non-Individualized Relief” provision in Section 24(A), if any provision of this Agreement is found to be partially or wholly invalid, illegal, or unenforceable:',
          'such provision shall be modified or restructured to the extent and in the manner necessary to render it valid, legal, and enforceable; or',
          'if such provision cannot be so modified or restructured, it shall be excised from the Agreement without affecting the validity, legality, or enforceability of any remaining provisions.',
          'Failure by iNSTAiNSTRU to enforce any provision(s) of the Agreement shall not be construed as a waiver of any provision or right.',
          'You acknowledge and agree that iNSTAiNSTRU may assign or transfer the Agreement without your consent. In such case, iNSTAiNSTRU will notify you of the assignment, and if legally required you may terminate the Agreement and cease using the Platform. Upon the effective date of the assignment: (a) iNSTAiNSTRU shall be relieved of all rights, obligations, and/or liabilities to you arising after that date, and (b) the assignee entity shall replace iNSTAiNSTRU for purposes of performance under the Agreement.',
          'You may not assign or transfer this Agreement without iNSTAiNSTRU’s prior written approval. Any assignment made in violation of this Section 23 is null and void.',
          'The Agreement will inure to the benefit of iNSTAiNSTRU, its successors, and assigns. All parts of the Agreement which, by their nature, should survive the expiration or termination of the Agreement shall continue in full force and effect afterward.'
        ]
      },
      {
        heading: '24. Jurisdiction-Specific Provisions, including Dispute Resolution',
        body: [
          'The terms in this Section apply to Users in the noted jurisdictions. To the extent that there are any discrepancies or inconsistencies between these Global Terms of Service and the following jurisdiction-specific provisions, the jurisdiction-specific provisions shall prevail, govern and control with respect to Users in those jurisdictions.',
          'Residents of the United States of America',
          'I. Dispute Resolution – Arbitration Agreement',
          'PLEASE READ THIS SECTION CAREFULLY — IT AFFECTS YOUR LEGAL RIGHTS AND GOVERNS HOW YOU AND iNSTAiNSTRU CAN BRING CLAIMS COVERED BY THIS ARBITRATION AGREEMENT. THIS SECTION WILL, WITH LIMITED EXCEPTION, REQUIRE YOU AND iNSTAiNSTRU TO SUBMIT CLAIMS TO BINDING AND FINAL ARBITRATION ON AN INDIVIDUAL BASIS.',
          'BY ENTERING INTO THIS AGREEMENT, YOU EXPRESSLY ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTAND AND AGREE, WITHOUT LIMITATION OR QUALIFICATION, TO BE BOUND BY THIS AGREEMENT AND YOU ACCEPT ALL OF ITS TERMS.',
          '(a) Agreement to Binding Arbitration',
          'IN EXCHANGE FOR THE BENEFITS OF THE SPEEDY, ECONOMICAL, AND IMPARTIAL DISPUTE RESOLUTION PROCEDURE OF ARBITRATION, YOU AND iNSTAiNSTRU MUTUALLY AGREE TO WAIVE YOUR RESPECTIVE RIGHTS TO RESOLUTION OF ALL DISPUTES OR CLAIMS COVERED BY THIS ARBITRATION AGREEMENT IN A COURT OF LAW BY A JUDGE OR JURY AND AGREE TO RESOLVE ANY DISPUTES BY BINDING ARBITRATION ON AN INDIVIDUAL BASIS AS SET FORTH HEREIN.',
          'This Arbitration Agreement is governed by the Federal Arbitration Act ("FAA") and survives termination of this Agreement and your relationship with iNSTAiNSTRU.',
          'To the fullest extent permitted by law, you and iNSTAiNSTRU agree to arbitrate any and all disputes and claims ("Claim(s)") relating to, arising from, or regarding your use of the Platform, your relationship with iNSTAiNSTRU, Lessons, or this Agreement (including previous versions), including Claims by or against iNSTAiNSTRU’s Affiliates.',
          'This includes, but is not limited to, claims involving: payments; wage or hour laws; compensation; reimbursement; termination; discrimination; harassment; retaliation; fraud; defamation; trade secrets; unfair competition; personal injury; property damage; emotional distress; any promotions or offers by iNSTAiNSTRU; the suspension or deactivation of your account; consumer-protection or antitrust laws; the Telephone Consumer Protection Act; the Fair Credit Reporting Act; and all other federal, state, or local statutory and common-law claims.',
          'Any dispute about the arbitrability of a Claim (including formation, scope, validity, or enforceability) shall be resolved by the arbitrator, except as expressly provided below. Non-arbitrable claims shall be stayed pending arbitration to the fullest extent permitted by law.',
          'YOU ACKNOWLEDGE THAT YOU AND iNSTAiNSTRU ARE WAIVING THE RIGHT TO SUE IN COURT OR HAVE A JURY TRIAL FOR ALL DISPUTES AND CLAIMS, UNLESS EXPRESSLY EXCLUDED HEREIN.',
          '(b) Prohibition of Class Actions and Non-Individualized Relief',
          'Except as otherwise required by law, any arbitration shall be limited to the Claim between iNSTAiNSTRU (and/or its Affiliates) and you individually.',
          'YOU AND iNSTAiNSTRU EACH WAIVE THE RIGHT TO PARTICIPATE AS A PLAINTIFF OR CLASS MEMBER IN ANY PURPORTED CLASS ACTION, CLASS-WIDE ARBITRATION, OR OTHER REPRESENTATIVE PROCEEDING ("CLASS ACTION WAIVER").',
          'Unless both parties agree otherwise, the arbitrator may not consolidate claims or preside over any class or representative proceeding. Disputes over the enforceability of this Class Action Waiver may be decided only by a civil court of competent jurisdiction. If the Waiver is deemed unenforceable for certain claims, those claims may proceed in court, while all other claims shall remain subject to individual arbitration.',
          '(c) Representative PAGA Waiver',
          'To the fullest extent permitted by law: (1) you and iNSTAiNSTRU agree not to bring a representative action under the California Private Attorneys General Act ("PAGA") or similar laws, and (2) any private-attorney-general-type claims may be arbitrated only on an individual basis (to determine whether you personally have been aggrieved).',
          'Disputes regarding the enforceability of this Representative PAGA Waiver may be resolved only by a civil court of competent jurisdiction. If the Waiver is found unenforceable, the unenforceable portion shall be severed, individual claims shall proceed in arbitration, and representative claims shall proceed in court (stayed pending arbitration of individual claims).',
          '(d) Rules and Logistics Governing Arbitration',
          'A claim must be filed with the American Arbitration Association ("AAA") using the Demand for Arbitration form available at www.adr.org, with notice to the other party.',
          'Arbitration shall be commenced and conducted under the AAA Rules and, where applicable, the AAA Consumer Rules, subject to the modifications in this Agreement. The arbitration shall be administered before a single mutually agreed arbitrator (or, failing agreement, appointed by the AAA).',
          'The arbitrator may allow reasonable discovery of relevant, non-privileged information. The arbitrator may award any individualized remedies available in court, but only in favor of the individual party seeking relief. The arbitrator shall issue a reasoned written decision.',
          'Claims shall be decided under applicable law, governed by their statute of limitations. The arbitrator’s award shall be final and may be entered in any court of competent jurisdiction.',
          'Multiple Similar Claims. If 25 or more substantially similar individual Demands are filed by or with the assistance of the same or coordinated counsel, the parties shall (i) select 10 bellwether cases to proceed first, (ii) stay the remaining Demands, and (iii) after final awards in the bellwethers, meet and confer in good faith regarding resolution of the remaining Demands. Arbitration fees for stayed Demands are not due unless and until the stay is lifted. This clause does not limit any individual’s right to pursue relief or the arbitrator’s ability to award individualized remedies permitted by law.',
          'Fees and Costs',
          'If iNSTAiNSTRU initiates arbitration, iNSTAiNSTRU pays all AAA fees.',
          'If a Student or Instructor files a Claim under $10,000, iNSTAiNSTRU pays all AAA fees unless the arbitrator finds the Claim frivolous.',
          'If a Claim exceeds $10,000, iNSTAiNSTRU pays all arbitration-unique costs, while the Student/Instructor pays no more than the local court filing fee (unless law or AAA Rules require less).',
          'Each party bears its own attorneys’ fees and ordinary litigation costs, except as allowed by law or AAA Rules.',
          'The arbitrator may award reasonable fees and costs to the prevailing party if permitted by law.',
          'Unless otherwise agreed, hearings with an Instructor occur remotely or in the county of the Instructor’s billing address; hearings with a Student occur remotely or in the county where the Student received Lesson services. If in-person AAA hearings are unavailable, they shall occur at the nearest available AAA location.',
          '(e) Exceptions to Arbitration',
          'This Arbitration Agreement does not require arbitration of:',
          'Workers’ compensation, disability, or unemployment-benefit claims;',
          'Individual small-claims-court actions;',
          'Applications for provisional remedies, preliminary injunctions, or temporary restraining orders relating to intellectual-property rights;',
          'Representative PAGA claims deemed non-arbitrable by a competent court; and',
          'Claims expressly excluded from arbitration by the FAA or governing law.',
          'Nothing prevents you from filing complaints or cooperating with government agencies such as the EEOC, U.S. Department of Labor, SEC, NLRB, or similar authorities, or from receiving any applicable whistleblower award.',
          '(f) Severability',
          'If any portion of this Arbitration Agreement is found illegal or unenforceable under law not preempted by the FAA, that portion shall be severed, and the remainder given full force and effect.',
          '(g) Opt Out of Arbitration Agreement (All Users). You may opt out of this arbitration agreement within 30 days of creating your account (or the effective date of any material change to this Section) by emailing support@instainstru.com with the subject "Arbitration Opt-Out," and including your name and the email tied to your account. Opting out affects only this arbitration clause and does not revoke consent to any prior or future arbitration agreements you may have with iNSTAiNSTRU.',
          '(h) Instructor Claims in Pending Class Action',
          'If you are a member of a putative wage-and-hour class action against iNSTAiNSTRU that was pending as of this Agreement’s effective date (“Pending Class Action”), this Arbitration Agreement shall not apply to your claims in that action. Those claims remain governed by the prior arbitration provisions applicable before this version took effect.',
          'II. Telephone Communications and Agreement to be Contacted',
          'You acknowledge that by providing your telephone number, you consent to receive calls or text messages—manual or automated—from iNSTAiNSTRU and its Affiliates, or from independent contractors (including Instructors) regarding your account, onboarding, scheduled Lessons, updates, outages, or your relationship with iNSTAiNSTRU—even if your number is listed on a Do Not Call registry.',
          'You may also enroll to receive promotional texts. By doing so, you agree to receive recurring automated marketing messages to your mobile number. Message frequency varies, and standard rates apply. You are not required to consent to promotional texts to purchase any goods or services.',
          'Transactional vs. Marketing. You consent to transactional calls and texts about your account and Lessons. Marketing texts are sent only with your separate prior express written consent. You may withdraw marketing consent at any time by replying STOP.',
          'Consent Records. We maintain time-stamped consent logs and honor STOP/HELP across all short codes and toll-free numbers used for the Platform. Message frequency varies; standard message and data rates may apply.',
          'No condition of purchase. Your consent to marketing is not a condition of purchasing any goods or services.',
          'To opt out of text messages, reply STOP, QUIT, END, CANCEL, or UNSUBSCRIBE to any message. You may receive one final confirmation text. If you opt out, we may still make non-automated calls as needed.',
          'III. Release',
          'TO THE EXTENT APPLICABLE, YOU HEREBY WAIVE THE PROTECTIONS OF CALIFORNIA CIVIL CODE § 1542, WHICH READS:',
          '“A GENERAL RELEASE DOES NOT EXTEND TO CLAIMS THAT THE CREDITOR OR RELEASING PARTY DOES NOT KNOW OR SUSPECT TO EXIST IN HIS OR HER FAVOR AT THE TIME OF EXECUTING THE RELEASE AND THAT, IF KNOWN BY HIM OR HER, WOULD HAVE MATERIALLY AFFECTED HIS OR HER SETTLEMENT WITH THE DEBTOR OR RELEASED PARTY.”',
          'If you are not a California resident, you waive similar protections under your jurisdiction’s laws.',
          'In consideration of the services provided by iNSTAiNSTRU, you release iNSTAiNSTRU from all claims, causes of action, damages, or losses arising from telephone calls or text messages, including those based on alleged violations of the Telephone Consumer Protection Act, Truth in Caller ID Act, Telemarketing Sales Rule, Fair Debt Collection Practices Act, or any similar laws.',
          'iNSTAiNSTRU and its Affiliates cannot and do not guarantee that any Personal Information you provide will not be misappropriated, intercepted, deleted, destroyed, or used by others.'
        ]
      },
      {
        heading: '25. Acknowledgement and Consent',
        body: [
          'I HEREBY ACKNOWLEDGE THAT I HAVE READ AND UNDERSTAND THE FOREGOING TERMS OF SERVICE, AS WELL AS THE PRIVACY POLICY, THE AUP, ALL OTHER TERMS INCORPORATED HEREIN AND THEREIN BY REFERENCE, AND AGREE THAT MY USE OF THE PLATFORM IS AN ACKNOWLEDGMENT OF MY AGREEMENT TO BE BOUND BY THE TERMS AND CONDITIONS OF THE AGREEMENT.'
        ]
      }
    ]
  },
  {
    id: 'privacy',
    title: 'iNSTAiNSTRU Privacy Policy',
    summary: 'Full privacy policy covering data collection, use, and rights.',
    updated: 'November 1, 2025',
    sections: [
      {
        heading: '1. Introduction',
        body: [
          'This Global Privacy Policy ("Privacy Policy") describes how iNSTAiNSTRU LLC and its subsidiaries (together as "iNSTAiNSTRU") collect, use, retain, disclose, and delete your Personal Information on the iNSTAiNSTRU websites and apps (the "Platform"). It also explains the legal rights and options with respect to your information depending on where you reside.',
          'By using the Platform, you confirm that you have read and understood this Privacy Policy, and each applicable Terms of Service (together referred to as the "Agreement").'
        ]
      },
      {
        heading: '2. General Terms',
        body: ['In this Privacy Policy:'],
        list: [
          'iNSTAiNSTRU LLC is referred to as "iNSTAiNSTRU," "we," "our," or "us."',
          'Users of the Platform (Students or Instructors) are referred to as "you."',
          'The "Platform" refers to iNSTAiNSTRU\'s websites (including www.instainstru.com and local variants, if any) and its mobile applications.',
          '"Terms of Service" refers to the applicable legal terms you agree to when you use one of our products or services. This Privacy Policy is incorporated into, and considered a part of, iNSTAiNSTRU\'s Terms of Service.',
          '"Personal Information" means information that can directly or indirectly identify, or can reasonably identify, an individual, to the extent regulated under applicable privacy laws.'
        ]
      },
      {
        heading: '3. Collection of Personal Information',
        body: [
          'We collect Personal Information directly from you when you provide it to us, or from your use of the Platform. Examples include:'
        ],
        list: [
          'Contact Information: first and last name, email address, physical address, and phone number.',
          'Billing Information: credit or debit card number, expiration date, security code, and billing ZIP code.',
          'Identity Information: date of birth and, depending on your location, government-issued identifiers and identification photos.',
          'Promotional Information: data provided when you participate in surveys, contests, or similar offerings.',
          'Job Applicant Information: employment and education history, references, LinkedIn profile, location, work authorization, or salary expectation.',
          'User-Generated Content: messages, photos, or communications shared on the Platform between users or with iNSTAiNSTRU.',
          'Booking Information: lesson details such as time, date, location, instructor skills, and rates.',
          'Driver\'s License and Vehicle Information: vehicle type, year, make, and model.',
          'Background Check Information: identity verification or criminal record results, where permitted by law.',
          'Data from Cookies and Similar Technologies: as described in our Cookie Policy.',
          'Device Data: device type, browser, operating system, internet service provider, regional or language settings, IP address, and device identifiers.',
          'Location Data: IP-based or GPS-based geolocation such as city or postal code.',
          'Service Use Data: pages viewed, browsing times, and interactions with emails or advertisements.',
          'Third-Party Information: data shared by trusted partners when you register or book through them.'
        ]
      },
      {
        heading: '4. Use of Personal Information',
        body: ['We use your Personal Information for business and commercial purposes, including:'],
        list: [
          'Operating and making the Platform available;',
          'Connecting you with other users to fulfill a lesson;',
          'Personalizing your experience on the Platform;',
          'Managing billing, preventing fraud, and maintaining a secure environment;',
          'Conducting identity verification and background checks, as permitted by law;',
          'Ensuring user safety online and offline;',
          'Maintaining the integrity of the Platform;',
          'Performing analytics and improving our services;',
          'Communicating transactional or promotional information;',
          'Providing customer support and assisting in dispute resolution;',
          'Advertising iNSTAiNSTRU\'s or partner products and services that may interest you;',
          'Enforcing the Terms of Service; and',
          'Complying with applicable laws.'
        ]
      },
      {
        heading: '5. Disclosure of Personal Information',
        body: ['We share Personal Information as follows:'],
        list: [
          'Subsidiaries: To promote and improve related services.',
          'Service Providers: To process Personal Information on our behalf for functions such as email origination, identity and background checks, fraud prevention and detection, billing, invoicing, support, customer relationship management, data analytics, marketing and advertising, hosting and communications, technical support, payment processing, and user onboarding.',
          'Promotions or Offers: With partners providing sweepstakes, contests, or promotions.',
          'Advertising: With third parties for ad delivery and measurement.',
          'Other Users: To resolve disputes or investigations related to Platform interactions.',
          'Legal Obligations: To comply with applicable law or respond to lawful requests from authorities.',
          'Mergers or Acquisitions: In connection with, or during negotiations of, a merger, acquisition, or sale of assets.'
        ]
      },
      {
        heading: '6. Retention of Personal Information',
        body: [
          'We retain your Personal Information for as long as necessary to provide services and comply with legal obligations. When it is no longer needed, we delete or deidentify it in accordance with applicable law.'
        ]
      },
      {
        heading: '7. Your Rights and Choices',
        body: [
          'Depending on where you live, you may have certain rights under regional or local laws (see Section 9).',
          'Opt-Out of Promotional Communications: You may opt out of marketing emails or notifications through your account settings, by clicking "unsubscribe" in promotional emails, or by texting "STOP" to opt out of marketing SMS messages. Transactional communications will still be sent.',
          'To exercise these rights, please submit a request and select "Consumer Rights Requests." We may need to verify your identity before processing certain requests.'
        ],
        list: [
          'Right to Access / Portability: Request access to the Personal Information we hold about you, including categories of data collected, sources, recipients, purposes, and specific pieces of information.',
          'Right to Correct / Delete: Update your information through Account Settings or request deletion. We may retain certain data to comply with legal obligations.',
          'Right to Non-Discrimination: You have the right to non-discriminatory treatment for exercising your privacy rights.'
        ]
      },
      {
        heading: '8. Contacting Us',
        body: [
          'If you have questions about this policy or our privacy practices, contact us at support@instainstru.com.'
        ]
      },
      {
        heading: '9. Jurisdiction-Specific Provisions',
        body: [
          'Right to Opt-Out of Sale: iNSTAiNSTRU does not sell Personal Information in the traditional sense. However, if certain advertising activities are interpreted as "sales" under the California Consumer Privacy Act (CCPA), you may opt out anytime by selecting Do Not Sell My Personal Information.',
          'California Residents: California residents may request a list of Personal Information categories disclosed for marketing purposes and the third parties receiving it. Submit a request here under "Consumer Rights Requests." Identity and residency verification may be required.'
        ]
      }
    ]
  },
  {
    id: 'cookie-policy',
    title: `${BRAND.name} Cookie Policy`,
    summary: `How we use cookies, pixels, and similar technologies to operate and improve the platform.`,
    updated: 'November 1, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'iNSTAiNSTRU uses cookies, unique identifiers, and other similar technologies, like pixels, to distinguish you from other users of our platform, provide our services to you, help collect data, and improve our platform.',
          'This Cookie Policy supplements our Privacy Policy and explains how and why we use cookies and other similar technologies. Any terms capitalized in this policy and not otherwise defined shall have the same meaning attributed to them in our Privacy Policy.',
          'When you visit our website, your browser may automatically transmit information to the site throughout the visit. In a similar way, when you use our mobile applications, we will access and use mobile device IDs to recognize your device. We use “cookies” and equivalent technologies to collect information through our website and Apps.',
          'Most browsers accept cookies by default. You can instruct your browser, by changing its settings, to decline or delete cookies. If you use multiple browsers on your device, you will need to instruct each browser separately. Your ability to limit cookies is subject to your browser settings and limitations. Exhibit A sets out the different categories of cookies that the iNSTAiNSTRU Platform uses and why we use them.'
        ]
      },
      {
        heading: 'Cookies',
        body: ['Cookies are small data files stored on your device that act as a unique tag to identify your browser.']
      },
      {
        heading: 'Persistent Cookies',
        body: [
          'Persistent cookies help with personalizing your experience, remembering your preferences, and supporting security features. Additionally, persistent cookies allow us to bring you advertising both on and off the iNSTAiNSTRU Platform. Persistent cookies may remain on your device for extended periods of time and generally may be controlled through your browser settings. We utilize persistent cookies that only iNSTAiNSTRU can read and use, and access mobile device IDs to:'
        ],
        list: [
          'save your login information for future logins to the iNSTAiNSTRU Platform;',
          'assist in processing items during checkout;',
          'hold session information;',
          'track user preferences.'
        ]
      },
      {
        heading: 'Session Cookies',
        body: [
          'Session cookies make it easier for you to navigate our website and expire when you close your browser. Unlike persistent cookies, session cookies are deleted from your computer when you log off from the iNSTAiNSTRU Platform and then close your browser. We utilize session ID cookies and similar technologies to:'
        ],
        list: [
          'enable certain features of the iNSTAiNSTRU Platform;',
          'better understand how you interact with the website and the iNSTAiNSTRU Platform;',
          'monitor usage by our Users and web traffic routing on the iNSTAiNSTRU Platform;',
          'track the number of entries in iNSTAiNSTRU promotions, sweepstakes, and contests;',
          'identify visited areas of the iNSTAiNSTRU Platform.'
        ]
      },
      {
        heading: 'Flash Cookies',
        body: [
          'We may use flash cookies (or Local Shared Objects) to personalize and enhance your visit. Via flash cookies we may store your preferences or display content based upon what you view on the Sites to personalize your visit.'
        ]
      },
      {
        heading: 'Pixel Tags',
        body: [
          'We and our third-party agents may use “pixel tags” (sometimes referred to as “web beacons” or “clear GIFs”). These or similar technologies are tiny graphic images and/or blocks of code with a unique identifier that are used to understand browsing activity and/or determine whether a specific action was performed.',
          'These are used by iNSTAiNSTRU or our third-party agents in connection with the iNSTAiNSTRU Platform and HTML-formatted email messages to, among other things, track the actions of Users and email recipients, determine the success of marketing campaigns, and compile statistics about Site usage and response rates.'
        ]
      },
      {
        heading: 'Marketing Services',
        body: [
          'We use Facebook cookies and pixels to help deliver our advertising on Facebook. This means you may see our ads when you use Facebook because you have visited our site, and to help integrate with our Facebook advertising services. In accordance with your Facebook privacy settings, please visit your Facebook privacy settings to learn more.',
          'iNSTAiNSTRU uses audience matching services to reach people (or people similar to those people) who have visited our Sites or are identified in one or more of our databases (“Matched Ads”). This is done by us uploading a hashed customer list to a third party or incorporating a pixel from another party into our own Sites, and the other party matching common factors between our data and their data or other datasets.',
          'For instance, we incorporate the Facebook pixel on our Sites and may share your email address with Facebook as part of our use of Facebook Custom Audiences.',
          'We also work with social networks and other third parties to help serve our ads. We identify certain characteristics and/or interests that we expect to be relevant to individuals interested in our services, and our ads are served to those individuals via social networks and other third parties which match these. Even if you have disabled certain cookies, our adverts may still be displayed to you through these channels. Please visit your social network preferences to understand more about these ads.',
          'To opt out of Matched Ads, please contact the applicable third-party agent directly.'
        ]
      },
      {
        heading: 'App and Location Technologies',
        body: [
          'We include technologies in our apps that are not browser-based like cookies and cannot be controlled by browser settings. For example, our Apps may include Software Development Kits (SDKs), which are code embedded in Apps that collect information about the App and your activity in the App. These SDKs allow us to track conversions and bring you advertising both on and off the iNSTAiNSTRU Platform. For example, we use the Facebook SDK as part of our use of Facebook Custom Audiences.',
          'You can stop all collection of information via an app by uninstalling the app. You can also reset your device Ad ID at any time through your device settings, which is designed to allow you to limit the use of information collected about you.',
          'If you do not want us to use your location anymore for the purposes set forth above, you should turn off the location services for the mobile application located in your device’s account settings, your mobile phone settings, and/or within the mobile application.'
        ]
      },
      {
        heading: 'Third-Party Cookies',
        body: [
          'Third-party cookies are placed by someone other than iNSTAiNSTRU. These third parties may gather browsing activity across multiple websites and multiple sessions. Third-party cookies are usually persistent cookies and are stored until you delete them or they expire based on the duration set in respect of each third-party cookie.',
          'For example, we may work with third-party advertisers who may place or read persistent cookies on your browser.',
          'A description of third-party cookies and similar technologies used by the Sites, along with their respective privacy policies and options for controlling your privacy on these platforms, is set out below:'
        ],
        list: [
          'DoubleClick: Google’s DoubleClick re-targeting cookie lets us serve personalized ads to you when you’re browsing other websites and social media platforms. You can control ad personalization on Google and partner websites in Google’s Privacy and Terms page.',
          'Facebook Impressions: We use Facebook Impressions to track the number of people that interact with our content on Facebook. This information is collected by Facebook and is provided to us under the terms of Facebook’s Privacy Policy. You can control the information that we receive from Facebook using the privacy settings in your Facebook account.',
          'LinkedIn Widgets: This tool enables visitors to engage with us via LinkedIn and show visitors relevant ads and personalized content on LinkedIn. To learn more about LinkedIn’s practices and to opt out, please visit LinkedIn’s Privacy Policy and Settings.',
          'Iterable: Email newsletters you elect to receive from us are transmitted through Iterable. Iterable uses pixel tag technology to determine whether an email has been opened. When you click any link in an email newsletter or marketing message you have elected to receive, Iterable recognizes that fact. This information is used in the aggregate to measure the rate at which emails are opened and various links are clicked, to measure user interests and traffic patterns, and to improve the content of the email newsletters and the services and features offered through the email newsletter and marketing messages. Because some of this information is linked to individual email addresses, it is personally identifiable. You can view Iterable’s privacy policy here.',
          'Bing Ads: We use Bing Ads to promote our company online and use the cookies provided by Bing to record completion of a transaction on our website. You can find out more about Bing cookies by visiting Bing’s Privacy Policy.',
          'Google Analytics: We use Google Analytics, a web analytics service. Google Analytics uses cookies to help iNSTAiNSTRU analyze how visitors use the Site(s). The information generated by cookies about your use of the Site(s) and the iNSTAiNSTRU Platform (including your IP address) will be transmitted to and stored by a Google server in the United States. Google uses this information for the purpose of evaluating your use of the Site(s), compiling reports on Site activity for Site operators, and providing Site operators with other services relating to Site activity and Internet usage. You can prevent the storage of data relating to your use of the Site(s) and created via the cookie (including your IP address) by Google, as well as the processing of this data by Google, by downloading and installing the browser plug-in available here. You can obtain additional information on Google Analytics’ collection and processing of data and data privacy and security at the following links: How Google Uses Information From Sites Or Apps That Use Our Services and Analytics Help.'
        ]
      },
      {
        heading: 'Information from Other Sources',
        body: ['We also collect information from other sources, including data brokers, social media networks, and publicly available sources.']
      },
      {
        heading: 'Your Choices and Managing Cookies',
        body: [
          'You can adjust your browser settings to enable you to stop accepting cookies or to prompt you before accepting a cookie from the websites you visit. Depending on what browser you use, you may manage your settings here: Internet Explorer, Safari, Chrome, Firefox, and Opera. If you do not accept cookies, however, you will not be able to use all portions or all functionalities of the iNSTAiNSTRU Platform.',
          'Your browser settings may allow you to automatically transmit a “Do Not Track” signal to online services you visit. Note, however, that there is currently no industry consensus as to what site and app operations should do with regard to these signals. Accordingly, unless and until the law is interpreted to require us to do so, we do not monitor or take action with respect to “Do Not Track” signals. For more information on “Do Not Track,” visit https://www.allaboutdnt.com.'
        ]
      },
      {
        heading: 'Contacting Us',
        body: [
          'If you have any questions about this Cookie Policy, the manner in which we or our third-party agents treat your Personal Information, the practices of the Site, or your dealings with the iNSTAiNSTRU Platform, please contact us at support@instainstru.com.'
        ]
      },
      {
        heading: 'Exhibit A',
        table: {
          headers: ['Type of Cookie', 'Purpose', 'iNSTAiNSTRU or 3rd Party'],
          rows: [
            [
              'Authentication Cookies',
              'These cookies (including local storage and similar technologies) tell us when you’re logged in, so we can customize your experience and connect your account information and settings.',
              'iNSTAiNSTRU'
            ],
            ['Localization', 'These cookies help provide a localized experience by showing you your local metro area.', 'iNSTAiNSTRU'],
            [
              'Site Features and Services',
              'These provide functionality that helps us deliver products and the iNSTAiNSTRU Platform. For example, cookies help you log in by pre-filling fields or help ensure older versions of web browsers can still view our Sites. We may also use cookies and similar technologies to help us provide you with social plugins and other customized content and experiences, including customized fonts.',
              'iNSTAiNSTRU, Facebook, LinkedIn, Amazon Hosting, Zopim, Polyfill, MyFonts Counter'
            ],
            [
              'Analytics and Research',
              'These are used to understand, improve, and research products and services, including when you access the iNSTAiNSTRU Platform and related websites and apps from a computer or mobile device. For example, we may use cookies to understand how you are using site features, to report on any errors in how the Site is functioning, to report to our vendors when content licensed from them is accessed, and to segment audiences for feature testing. We and our partners may use these technologies and the information we receive to improve and understand how you use websites, apps, products, services, and ads.',
              'Google Analytics, HeapAnalytics, MixPanel, BugSnag, Google Tag Manager, Optimizely'
            ],
            [
              'Interest-Based Advertising',
              'Things like cookies and pixels are used to deliver relevant ads, track ad campaign performance and efficiency, and to understand your interests from your online activity on the Site, mobile applications, and other websites and apps. For example, we and our ad partners may rely on information gleaned through these cookies to serve you ads that may be interesting to you on other websites, and in doing that, your information (which will not contain your name, email address, or other "real-world" identifiers) will be shared with other platforms in the digital advertising ecosystem, all involved in assisting the delivery, purchase, reporting, and analysis of digital advertising. Similarly, our advertisers may use a cookie, attribution service, or another similar technology to determine whether we have served an ad and how it performed, or provide us with information about how you interact with them. Please note that even if you opt out of interest-based advertising by a third party, these tracking technologies may still collect data for other purposes, including analytics, and you may still see ads from us -- but the ads will not be targeted based on behavioral information about you and may therefore be less relevant to your interests. You can instruct your browser, by changing its options, to stop accepting cookies or to prompt you before accepting a cookie from the websites you visit. To successfully opt out, you must have cookies enabled in your web browser. Please see the instructions for your browser for information on cookies and how to enable them. Your opt-out only applies to the web browser you use, so you must opt out of each web browser on each device that you use. Once you opt out, if you delete cookies saved by your browser, you may need to opt out again. For more information about targeting and advertising cookies and how you can opt out, you can visit the Network Advertising Initiative opt-out page, the Digital Advertising Alliance US opt-out page, YourAdChoices Canada, or YourOnlineChoices EU.',
              'Multiple third-party ad networks'
            ]
          ]
        }
      }
    ]
  },
  {
    id: 'acceptable-use',
    title: 'iNSTAiNSTRU Platform Acceptable Use Policy (AUP)',
    summary: 'Additional conditions that govern how you may use the iNSTAiNSTRU Platform.',
    updated: 'November 3, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'This iNSTAiNSTRU Platform Acceptable Use Policy (this "AUP") forms a part of iNSTAiNSTRU\'s Global Terms of Service (the "Terms"). Capitalized terms used, but not defined, in this AUP will have the definitions as set out in the Terms.',
          'This AUP establishes additional conditions that apply to your use of the Platform. Users must comply with this AUP in their use of the Platform.'
        ]
      },
      {
        heading: 'Prohibited Uses',
        body: ['Without limitation, you may not use the Platform, and you may not permit any third party, to:'],
        list: [
          'Defame, abuse, harass, stalk, threaten, intimidate, misrepresent, mislead, or otherwise violate the rights (such as, but not limited to, rights of privacy, confidentiality, reputation, and publicity) of others, including Users and/or iNSTAiNSTRU staff;',
          'Publish, post, upload, distribute, or disseminate any content or information, or files that contain software or other materials that infringe upon or violate the intellectual property rights or rights of privacy or publicity of iNSTAiNSTRU or any other User or third party, or which are profane, defamatory, obscene, or unlawful;',
          'Upload files or scripts that may or are designed to damage, copy, lock out, or take control of the Platform or any User\'s computer, such as Trojan horses, corrupt files, SQL injections, worms, timebombs, cancelbots, or any other files or software;',
          'Advertise or offer to sell any goods or services for any commercial purpose that are not relevant to the Lesson services;',
          'Post or complete a Lesson requiring a User to (1) purchase or obtain gift cards or money orders, (2) purchase high value items (over 300 USD / 300 GBP / 300 EUR, as applicable in your country) without obtaining pre-authorization from iNSTAiNSTRU, (3) travel into different countries during the performance of a Lesson, (4) provide ridesharing or other peer-to-peer transportation services, (5) post ratings or reviews on any third-party website in breach of such third party\'s terms of use, or (6) otherwise engage in activity that is illegal or deemed to be dangerous, harmful, or otherwise inappropriate by iNSTAiNSTRU in its sole discretion;',
          'Conduct or forward surveys, contests, pyramid schemes, or chain letters;',
          'Impersonate another person or User, or allow any other person or entity to use another User\'s profile to post or view comments (except as may be expressly permitted in the Terms under Section 2(E)(ii) for Student Agents).'
        ]
      },
      {
        heading: 'Additional Restrictions',
        body: ['Additionally, you may not, and you may not permit any third party to:'],
        list: [
          'Use the Platform or use or perform the Lesson services in violation of the Agreement (including this AUP);',
          'Use the Platform or use or perform the Lesson services in any manner or for any purpose (1) other than as expressly set out in the Agreement (including, but not limited to, any journalistic, academic, investigative, or unlawful purpose), (2) that is unauthorized or illegal (including, but not limited to, posting or performing a Lesson in violation of local, state, provincial, national, or international law), (3) that is false or misleading (whether directly or by omission or failure to update information), or (4) to access or obtain iNSTAiNSTRU\'s trade secret information (or attempt to do so);',
          'Post or upload any content to the Platform (1) that is offensive and/or harmful (including, but not limited to, content that advocates, endorses, condones, or promotes racism, bigotry, hatred, or physical harm of any kind against any individual or group of individuals, or that exploits people in an abusive, violative, or sexual manner), or (2) for which you have not obtained the necessary rights and permissions;',
          'Post the same Lesson repeatedly ("spamming");',
          'Download any file posted by another User that you know, or reasonably should know, cannot be legally distributed through the Platform;',
          'Restrict or inhibit any other User from using and enjoying the Public Areas;',
          'Imply or state that any statements you make (whether on or off the iNSTAiNSTRU Platform) are endorsed by iNSTAiNSTRU, without the prior written consent of iNSTAiNSTRU;',
          'Use a robot, spider, manual, meta tag, "hidden text," agent, script, and/or automatic processes or devices to data-mine, data-crawl, scrape, collect, mine, republish, redistribute, transmit, sell, license, download, manage, or index the iNSTAiNSTRU Platform, or the electronic addresses or personal information of others, in any manner;',
          'Frame or utilize framing techniques to enclose all or any portion of the Platform;',
          'Hack or interfere with the Platform, its servers, or any connected networks;',
          'Adapt, alter, license, sublicense, or translate the Platform for your own personal or commercial use;',
          'Remove, alter, or misuse, visually or otherwise, any copyrights, trademarks, or proprietary marks or rights owned by iNSTAiNSTRU and Affiliates;',
          'Solicit for any other business, website, or service, or otherwise contact Users for employment, contracting, or any purpose not permitted by the Agreement;',
          'Collect usernames, email addresses, or other personal information of Users by electronic or other means;',
          'Attempt to circumvent the payments system, PSP, or service charge in any way (including, but not limited to, making or processing payments for Lessons outside of the Platform, providing inaccurate information on invoices, or otherwise invoicing in a fraudulent manner);',
          'Register (1) under different usernames, identities, or false identities (including after your account has been suspended or terminated), (2) under multiple usernames or false identities, or (3) using inaccurate information (including using a false or disposable email or phone number);',
          'Use tools with the goal of masking your IP address (like the TOR network);',
          'Copy, download, use, redesign, reconfigure, or retransmit anything from the iNSTAiNSTRU Platform without iNSTAiNSTRU\'s express prior written consent, and/or if applicable, the consent of the holder of the rights to the User Generated Content;',
          'Use any artificial intelligence technologies to create or generate a Platform account, or to impersonate another person or User;',
          'Submit any part of the Platform (including, without limitation, any iNSTAiNSTRU information) into any artificial intelligence technologies.'
        ]
      }
    ]
  },
  {
    id: 'payments',
    title: 'Fees, Payments, and Cancellation Supplemental Terms',
    summary: 'How fees, payments, and cancellations work on the iNSTAiNSTRU Platform.',
    updated: 'November 3, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'THESE FEES, PAYMENTS AND CANCELLATION SUPPLEMENTAL TERMS ("Fees and Payments Terms") form part of iNSTAiNSTRU\'s Global Terms of Service (the "Terms") and apply to each User\'s access to and use of the Platform, and the fees and payments associated with such access and use.',
          'Capitalized terms used, but not defined, in these Fees and Payments Terms will have the definitions as set out in the Terms.'
        ]
      },
      {
        heading: 'A. Lesson Payment and Other Amounts Owed by the Student',
        body: [
          'All amounts owed and/or to be paid by you shall be set out in an invoice ("Invoice(s)"), which will include the Lesson-related fees and iNSTAiNSTRU fees, each as described in more detail below in this Section A.',
          'By providing a payment method, and upon receipt (whether through the Platform or via text or email) that the Lesson has been completed, you authorize us to process your existing payment method. If we are unable to charge your existing payment method, you authorize us to use any payment methods you have previously linked to your account. To update your existing payment preferences, go to Your Account -> Billing Info.',
          'You acknowledge and agree that we may prevent you from booking future Lessons if any amounts remain outstanding on your account. Unless otherwise expressly stated in this Agreement, all fees (including, without limitation, the Lesson Payment and all iNSTAiNSTRU fees) are non-refundable.'
        ]
      },
      {
        heading: '1. Lesson-related fees',
        body: ['The Student is responsible for paying the following associated with each Lesson:'],
        list: [
          'the fee for the Lesson, at the Instructor\'s rates and as agreed-upon by the Student and the Instructor (the "Lesson Payment"),',
          'any out-of-pocket expenses agreed-upon by the Student and the Instructor and submitted by the Instructor in connection with the Lesson,',
          'a tip or gratuity, as applicable, which may be added to the Invoice by, or at the direction of, the Student (all of which shall go directly to the Instructor),',
          'taxes or similar charges, as described in Section E below,',
          'a credit-card processing fee, as applicable, and',
          'taxes or similar charges, as described in Section E below.'
        ]
      },
      {
        heading: '2. iNSTAiNSTRU fees',
        body: ['In addition to the amounts owed for the Lesson as set out in Section A(1) above, iNSTAiNSTRU charges, and the Student is responsible for paying, the following fees associated with each Lesson:'],
        list: [
          'the service charge that iNSTAiNSTRU assesses to the Student for access to and information regarding Instructors;',
          'the Trust & Support fee that iNSTAiNSTRU assesses for customer support, services in support of the platform\'s guarantees, and other operational services;',
          'taxes or similar charges, as described in Section E below; and',
          'applicable cancellation charges (see Section F below for details).'
        ],
        bodyAfterList: [
          'iNSTAiNSTRU reserves the right to change its fees at any time and will notify Students of any fee changes in accordance with Section 17 of the Terms.',
          'If you disagree with an iNSTAiNSTRU fee change, you may cease using the Platform and terminate the Agreement at any time pursuant to Section 7 of the Terms. Instructors have no authority to, and may not, modify all or any part of iNSTAiNSTRU\'s fees.'
        ]
      },
      {
        heading: 'B. Amounts Owed by Instructors',
        body: [
          'Instructors will be responsible for (1) paying registration fees, if applicable, and (2) repaying to iNSTAiNSTRU or the PSP any erroneous payments or other amounts received by the Instructor.'
        ]
      },
      {
        heading: 'C. Payment Service Provider (PSP)',
        body: [
          'All amounts owed and/or to be paid by any User must be paid through the PSP.',
          'The Student will be required to provide their payment-method details to iNSTAiNSTRU and the PSP. The Instructor will be required to set up an account with the PSP, which requires registration with the PSP, consent to the terms of service of the PSP (the "PSP Services Agreement"), and completion of a vetting process and/or account validation.',
          'iNSTAiNSTRU is not a party to any PSP Services Agreement and has no obligations, responsibility, or liability to any Instructor or other party under any PSP Services Agreement.'
        ]
      },
      {
        heading: 'D. Fraud',
        body: [
          'Notwithstanding anything herein to the contrary, the Student will not be held responsible for transactions that are identified by iNSTAiNSTRU as potential or confirmed fraud; provided that the Student did not contribute to or cause (directly or indirectly, in any part) such fraud.',
          'In these instances, a transaction may be declined, frozen, or held until investigation is complete.'
        ]
      },
      {
        heading: 'E. Sales Tax Collection and Remittance',
        body: [
          'Users of the Platform may be liable for taxes or similar charges (including VAT, if applicable in the country where the Lesson is performed) which are imposed on the Lessons performed and/or fees paid under the Agreement and must be collected and/or paid.',
          'In certain jurisdictions, applicable rules require that we collect and/or report tax and/or revenue information about you to applicable tax authorities. You agree that iNSTAiNSTRU may issue, on your behalf, receipts or similar documentation to facilitate accurate tax reporting, and use of your account may be paused until such documentation is provided.',
          'Notwithstanding anything herein to the contrary, however:',
          'Instructors remain fully responsible and liable for, and in charge of, compliance with all tax obligations applicable to the Instructor and the Lessons (including performance thereof), including, without limitation, filing their tax returns (such as, as applicable, VAT) and paying taxes (such as, as applicable, VAT) relating to the Lessons performed by them for the benefit of their Students. Instructors should consult with their own tax advisors to ensure compliance with applicable tax and reporting requirements.',
          'iNSTAiNSTRU is neither responsible nor liable for ensuring Users\' compliance with applicable tax obligations. Without limitation, iNSTAiNSTRU shall not be held responsible for any breach of an Instructor\'s tax obligations, including (without limitation) that iNSTAiNSTRU shall not be held jointly and severally liable for taxes, interest on overdue taxes, or for any penalties or fines that would be owed by the Instructor.',
          'iNSTAiNSTRU may (i) request the Instructor to confirm and/or demonstrate that they are up to date with their tax obligations (including social contributions, if applicable); and (ii) deactivate an Instructor\'s account or limit their use of or remove the Instructor from the Platform upon (1) a determination from the applicable tax authorities that such Instructor has failed to comply with tax obligations (such as VAT), or (2) if the Instructor is unable or unwilling to confirm and/or demonstrate their compliance with their tax obligations, upon request.'
        ]
      },
      {
        heading: 'F. Cancellation Fees',
        body: [
          'Students may cancel a Lesson at any time. However, the Student may be billed a cancellation fee under certain circumstances. Please consult the Cancellation Policy available through support@instainstru.com or within your account dashboard.'
        ]
      }
    ]
  },
  {
    id: 'contact-details',
    title: 'iNSTAiNSTRU Contact Details Supplemental Terms',
    summary: 'How to reach iNSTAiNSTRU for legal or policy questions.',
    updated: 'November 3, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'These iNSTAiNSTRU Contact Details Supplemental Terms ("Contact Details") form part of iNSTAiNSTRU\'s Global Terms of Service (the "Terms") and apply to all Users\' access to and use of the Platform.',
          'Capitalized terms used but not defined in these Contact Details will have the meanings set out in the Terms.'
        ]
      },
      {
        heading: 'Get in Touch',
        body: [
          'If you have any questions about the Agreement, the Platform, or any related policies, please contact us using the details below:',
          'support@instainstru.com',
          'Attention: Legal'
        ]
      }
    ]
  },
  {
    id: 'sms-terms',
    title: 'iNSTAiNSTRU SMS Terms and Conditions',
    summary: 'Rules for receiving SMS messages from iNSTAiNSTRU.',
    updated: 'November 3, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Pursuant to the provisions of Section 28 of the iNSTAiNSTRU Global Terms of Service, you may receive messages that include Instructor Status updates, Lesson Reminders and Receipts, two-factor authentication (2FA) codes, and promotional or service-related messages that may be sent to Students and Instructors on iNSTAiNSTRU.',
          'Message frequency varies.',
          'Carriers are not liable for delayed or undelivered messages. Message and data rates may apply.',
          'Reply HELP for assistance.',
          'Reply STOP to unsubscribe.',
          'For our Privacy Policy, please visit the Privacy Policy or contact support@instainstru.com.'
        ]
      }
    ]
  },
  {
    id: 'referral-program',
    title: 'iNSTAiNSTRU Referral Program Terms and Conditions',
    summary: 'Details for the Give $20 / Get $20 referral program.',
    updated: 'November 3, 2025',
    sections: [
      {
        heading: 'Overview',
        body: [
          'These iNSTAiNSTRU Referral Program Terms and Conditions ("Referral Terms") govern participation in iNSTAiNSTRU\'s "Give $20 / Get $20" referral program (the "Program").',
          'These Referral Terms form part of, and are subject to, the iNSTAiNSTRU Global Terms of Service and Privacy Policy. By sharing a referral link, inviting a friend, or redeeming a referral reward, you agree to these Terms.'
        ]
      },
      {
        heading: '1. Overview',
        body: [
          'The iNSTAiNSTRU Referral Program allows Users (both Instructors and Students) to earn referral rewards ("Referral Rewards") by inviting new Users to sign up and book a qualifying lesson through the iNSTAiNSTRU Platform.',
          'We may change, suspend, or terminate the Program at any time for any reason. Any changes will apply prospectively.'
        ]
      },
      {
        heading: '2. Eligibility',
        body: ['To participate, you must:'],
        list: [
          'Have an active iNSTAiNSTRU account in good standing.',
          'Reside in a jurisdiction where the Program is legally permitted.',
          'Be in full compliance with the iNSTAiNSTRU Global Terms of Service.'
        ],
        bodyAfterList: [
          'New Users ("Referees") must create an iNSTAiNSTRU account with the Referrer\'s unique link or code, complete their first lesson valued at 75 USD or more within 30 days of signup, and be new to the Platform (one referral reward per household; self-referrals are prohibited).'
        ]
      },
      {
        heading: '3. How the Program Works',
        body: [
          'Eligible Users ("Referrers") can access their unique referral code or link through their iNSTAiNSTRU account.',
          'The Referrer may share this link privately with friends, family, or colleagues they personally know ("Friends").',
          'When a Friend signs up using the referral link and completes an eligible first lesson, both the Referrer and the Referee receive a 20 USD iNSTAiNSTRU credit ("Referral Reward").',
          'Rewards are typically issued within 48 hours after the qualifying lesson is completed.',
          'If the qualifying lesson is canceled or refunded, the corresponding Referral Reward may be revoked.'
        ]
      },
      {
        heading: '4. Reward Use',
        body: [
          'Referral Rewards are issued as iNSTAiNSTRU credits and automatically apply at checkout when booking a new lesson of 75 USD or more.',
          'Credits:'
        ],
        list: [
          'Have no cash value and cannot be transferred.',
          'May not be combined with other promo codes, offers, or discounts.',
          'May only be redeemed on the iNSTAiNSTRU Platform.',
          'Only one credit can be applied per transaction.',
          'Rewards may not be used toward taxes, tips, background check fees, or other non-lesson fees.'
        ]
      },
      {
        heading: '5. Expiration and Forfeiture',
        body: [
          'Referral credits expire 90 days from the date of issuance (unless otherwise stated in your rewards dashboard).',
          'Unused or expired credits are forfeited upon any of the following:'
        ],
        list: [
          'Account closure.',
          'Violation of these Referral Terms.',
          'Misuse of the Program (as described in Section 8 below).'
        ]
      },
      {
        heading: '6. Verification and Limits',
        body: [
          'Referral Rewards are subject to verification and may be withheld, delayed, or revoked at iNSTAiNSTRU\'s sole discretion.',
          'Rewards may differ based on region or promotional period.',
          'A single User may not earn more than 500 USD in referral credits per calendar year.',
          'Referral links may not be distributed via coupon sites, paid ad networks, or public forums without iNSTAiNSTRU\'s prior written consent.'
        ]
      },
      {
        heading: '7. Fair Use and Prohibited Conduct',
        body: [
          'We may suspend or revoke referral privileges if we suspect fraud, spam, reseller activity, fake accounts, or other abuse.',
          'Specifically, Users may not:'
        ],
        list: [
          'Refer themselves or create multiple accounts.',
          'Use bots, scripts, or automated tools to generate signups.',
          'Mislead or misrepresent the nature of the Program.',
          'Post referral links publicly or in ways that violate anti-spam or privacy laws.'
        ],
        bodyAfterList: [
          'Each Referrer is considered the sender of any referral communication and must comply with all applicable laws, including CAN-SPAM and other anti-spam regulations.'
        ]
      },
      {
        heading: '8. Disclaimer of Warranties',
        body: [
          'THE PROGRAM AND THE iNSTAiNSTRU PLATFORM ARE PROVIDED ON AN "AS IS" AND "AS AVAILABLE" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, WHETHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION, WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.',
          'iNSTAiNSTRU DOES NOT GUARANTEE THAT REFERRAL REWARDS WILL BE AVAILABLE OR ERROR-FREE, NOR THAT THEY WILL BE ISSUED IN EVERY CASE.'
        ]
      },
      {
        heading: '9. Limitation of Liability',
        body: [
          'TO THE FULLEST EXTENT PERMITTED BY LAW, THE MAXIMUM LIABILITY OF iNSTAiNSTRU, ITS AFFILIATES, AND CORPORATE PARTNERS ARISING OUT OF OR IN CONNECTION WITH THE PROGRAM SHALL NOT EXCEED 100 USD.',
          'You agree to indemnify, defend, and hold harmless iNSTAiNSTRU and its Affiliates from any claims, losses, or damages arising out of your participation in the Program or your violation of these Terms.'
        ]
      },
      {
        heading: '10. Right to Cancel, Modify, or Terminate',
        body: [
          'iNSTAiNSTRU reserves the right to cancel, modify, or terminate the Program - or any User\'s participation - at any time, for any reason, including where fraud or abuse is suspected.',
          'If the Program is terminated, iNSTAiNSTRU will honor Referral Rewards already earned, unless termination occurs due to fraudulent or abusive conduct.'
        ]
      },
      {
        heading: '11. Contact',
        body: [
          'If you have any questions about these Referral Terms or the Program, please contact:',
          'Email: support@instainstru.com',
          'Attention: Legal'
        ]
      }
    ]
  },
  {
    id: 'instructors',
    title: 'Instructor Participation Agreement',
    summary: 'Expectations and safety commitments for instructors.',
    updated: 'November 1, 2025',
    sections: [
      {
        heading: '1. Eligibility & Background Review',
        body: [
          'Instructors must be at least 18 years old, legally able to work in their service area, and maintain any required certifications. We conduct background screenings and repeat verifications periodically to maintain safety.'
        ]
      },
      {
        heading: '2. Lesson Quality Standards',
        list: [
          'Arrive prepared, on time, and ensure lesson plans align with the student\'s stated goals.',
          'Communicate changes promptly through the platform messaging tools.',
          'Maintain a lesson rating of 4.6 or higher to stay active on the platform.'
        ]
      },
      {
        heading: '3. Communication & Off-Platform Policy',
        body: [
          'Use the in-app messaging system for scheduling, updates, and support so we can assist if issues arise. Directly soliciting students for off-platform lessons violates the agreement and may result in account closure.'
        ]
      },
      {
        heading: '4. Safety & Professional Conduct',
        list: [
          'Follow all applicable laws, including child safety requirements and mandated reporting obligations.',
          'Prohibit discrimination or harassment based on protected characteristics.',
          'Ensure lesson environments are safe, appropriately equipped, and respectful of student privacy.'
        ]
      }
    ]
  }
];

const DEFAULT_SELECTED_ID = LEGAL_DOCUMENTS[0]?.id ?? 'terms';

export default function LegalResourceCenter() {
  const { user, isAuthenticated } = useAuth();
  const hashId = useSyncExternalStore(
    (onStoreChange) => {
      if (typeof window === 'undefined') return () => {};
      const handleChange = () => onStoreChange();
      window.addEventListener('hashchange', handleChange);
      return () => window.removeEventListener('hashchange', handleChange);
    },
    () => (typeof window === 'undefined' ? '' : window.location.hash.replace('#', '').trim()),
    () => ''
  );
  const selectedId = useMemo(() => {
    if (hashId && LEGAL_DOCUMENTS.some((doc) => doc.id === hashId)) {
      return hashId;
    }
    return DEFAULT_SELECTED_ID;
  }, [hashId]);

  const selectedDocument = useMemo<LegalDocument | null>(() => {
    return LEGAL_DOCUMENTS.find((doc) => doc.id === selectedId) ?? LEGAL_DOCUMENTS[0] ?? null;
  }, [selectedId]);

  if (!selectedDocument) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4 sticky top-0 z-40">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#5f1aa4] transition-colors cursor-pointer">
              {BRAND.name}
            </h1>
          </Link>
          <div className="flex items-center gap-4">
            {isAuthenticated ? (
              <>
                {user && hasRole(user, RoleName.STUDENT) && (
                  <Link
                    href="/student/lessons"
                    className="text-gray-700 hover:text-[#7E22CE] font-medium transition-colors"
                  >
                    My Lessons
                  </Link>
                )}
                <UserProfileDropdown />
              </>
            ) : (
              <Link
                href="/login"
                className="px-4 py-2 bg-[#7E22CE] text-white rounded-lg hover:bg-[#5f1aa4] transition-colors font-medium"
              >
                Sign up / Log in
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <span className="text-sm uppercase tracking-[0.18em] text-gray-500">Legal Center</span>
          <h1 className="mt-2 text-4xl font-bold text-gray-900">Policies &amp; Agreements</h1>
          <p className="mt-3 max-w-3xl text-base text-gray-600">
            Transparency matters. Browse the latest versions of our terms, privacy commitments, and instructor expectations. Each article lives in a single place so you always know where to find the most current language.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          <aside className="lg:w-72 flex-shrink-0">
            <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-200 px-5 py-4">
                <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Articles in this section</h2>
              </div>
              <nav className="flex flex-col divide-y divide-gray-100" aria-label="Legal documents">
                {LEGAL_DOCUMENTS.map((doc) => {
                  const isActive = doc.id === selectedDocument.id;
                  return (
                    <button
                      key={doc.id}
                      type="button"
                      onClick={() => {
                        if (typeof window !== 'undefined') {
                          window.location.hash = doc.id;
                        }
                      }}
                      className={cn(
                        'text-left px-5 py-4 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE]',
                        isActive ? 'bg-[#7E22CE]/10 text-[#4a1a85]' : 'hover:bg-gray-50 text-gray-700'
                      )}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      <p className="text-sm font-semibold">{doc.title}</p>
                      <p className="mt-1 text-xs text-gray-500">{doc.summary}</p>
                    </button>
                  );
                })}
              </nav>
            </div>
          </aside>

          <article id={selectedDocument.id} className="flex-1 rounded-2xl border border-gray-200 bg-white shadow-sm p-8">
            <header className="border-b border-gray-200 pb-6 mb-6">
              <h2 className="text-3xl font-semibold text-gray-900">{selectedDocument.title}</h2>
              <p className="mt-2 text-sm text-gray-500">Last updated {selectedDocument.updated}</p>
            </header>

            <div className="space-y-10 text-gray-700">
              {selectedDocument.sections.map((section) => (
                <section key={`${selectedDocument.id}-${section.heading}`}>
                  <h3 className="text-xl font-semibold text-gray-900">{section.heading}</h3>
                  {section.body?.map((paragraph, index) => (
                    <p key={index} className="mt-3 leading-7">
                      {paragraph}
                    </p>
                  ))}
                  {section.list && (
                    <ul className="mt-4 list-disc space-y-2 pl-6">
                      {section.list.map((item, index) => (
                        <li key={index} className="leading-7">
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                  {section.bodyAfterList?.map((paragraph, index) => (
                    <p key={`after-${index}`} className="mt-3 leading-7">
                      {paragraph}
                    </p>
                  ))}
                  {section.table && (
                    <div className="mt-6 overflow-x-auto">
                      <table className="w-full border-collapse text-sm text-gray-700">
                        <thead>
                          <tr>
                            {section.table.headers.map((header, index) => (
                              <th
                                key={index}
                                className="border-b border-gray-200 px-4 py-3 text-left text-gray-900 text-sm font-semibold"
                              >
                                {header}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {section.table.rows.map((row, rowIdx) => (
                            <tr key={rowIdx} className="align-top">
                              {row.map((cell, cellIdx) => (
                                <td key={cellIdx} className="border-b border-gray-200 px-4 py-3">
                                  {cell}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              ))}

              <section className="rounded-xl bg-purple-50 border border-purple-100 px-4 py-5 text-sm text-purple-900">
                <h4 className="text-base font-semibold">Need clarification?</h4>
                <p className="mt-2">
                  Our team is happy to help. Email{' '}
                  <a href={`mailto:${BRAND.email.support}`} className="font-medium underline">
                    {BRAND.email.support}
                  </a>{' '}
                  with the subject line &quot;Legal question&quot; and we will respond within two business days.
                </p>
              </section>
            </div>
          </article>
        </div>
      </div>
    </div>
  );
}

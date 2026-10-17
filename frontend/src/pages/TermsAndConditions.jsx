import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FileText } from 'lucide-react';
import Brand from '../components/site/Brand';
import SiteFooter from '../components/site/SiteFooter';
import '../styles/site.css';
import '../styles/legal.css';

function TermsAndConditions() {
  return (
    <div className="zenpos-site legal-page">
      <header className="legal-header">
        <Brand />
        <Link className="legal-back-link" to="/"><ArrowLeft size={15} /> Back to home</Link>
      </header>
      <main className="legal-main">
        <div className="legal-kicker"><FileText size={15} /> SERVICE TERMS</div>
        <h1>Terms and conditions</h1>
        <p className="legal-intro">These terms describe the basic rules for accessing and using ZenPOS, a point-of-sale and retail operations platform.</p>
        <p className="legal-updated">Last updated: 17 October 2026</p>

        <section className="legal-section">
          <h2>1. Agreement and eligibility</h2>
          <p>By accessing or using ZenPOS, you agree to these terms and any additional terms presented for features or services you enable. If you use ZenPOS for a shop, employer or other organization, you confirm that you are authorized to do so. If you do not agree, do not use the service.</p>
          <p>Your organization may have separate agreements with the service provider. Those agreements may govern account provisioning, fees, support and service levels.</p>
        </section>

        <section className="legal-section">
          <h2>2. Accounts and access</h2>
          <p>Accounts are intended for authorized users. You must provide accurate account information where requested, keep credentials confidential, and promptly report suspected compromise. Do not share accounts or attempt to bypass authentication, role permissions, organization boundaries or other security controls.</p>
          <p>Organization administrators are responsible for assigning suitable roles, reviewing access, and removing access when a staff member no longer needs it. Actions performed through your account may be attributed to that account.</p>
        </section>

        <section className="legal-section">
          <h2>3. Acceptable use</h2>
          <p>You may use ZenPOS only for lawful business operations and in accordance with these terms. You must not:</p>
          <ul>
            <li>access another organization's records without authorization;</li>
            <li>probe, disrupt, overload or attempt to compromise the service or its infrastructure;</li>
            <li>upload malicious code or use the service for fraud or unlawful activity;</li>
            <li>misuse personal information or enter data you have no lawful right to process;</li>
            <li>attempt to reverse engineer or interfere with security features except where applicable law permits it.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2>4. Business records and responsibility</h2>
          <p>Your organization is responsible for the accuracy, completeness and lawfulness of the products, prices, tax settings, customer details, stock movements, sales and other records entered into ZenPOS. Review records and reports before relying on them for operational, financial or statutory decisions.</p>
          <p>ZenPOS provides tools to record and manage business activity; it does not replace professional accounting, tax, legal or business advice. You remain responsible for meeting applicable tax, consumer, employment, licensing and record-keeping obligations, including any required eTIMS processes.</p>
        </section>

        <section className="legal-section">
          <h2>5. Payments and third-party services</h2>
          <p>Payment methods, M-Pesa workflows, tax integrations and other third-party services may depend on separate providers, eligibility, configuration and availability. A status shown in ZenPOS may reflect information returned by an integration and should be checked with the relevant provider where necessary.</p>
          <p>Third-party services are governed by their own terms and privacy notices. ZenPOS is not responsible for third-party systems beyond the responsibilities imposed by applicable law or an agreement with you.</p>
        </section>

        <section className="legal-section">
          <h2>6. Availability, maintenance and changes</h2>
          <p>We aim to keep ZenPOS useful and available, but uninterrupted access is not guaranteed. The service may be unavailable because of maintenance, upgrades, network or hosting problems, security incidents, or circumstances outside reasonable control. Features may be changed, suspended or discontinued as the platform develops.</p>
          <p>Offline or locally queued functionality, if enabled, may have limits. Users should confirm that important transactions have synchronized and been recorded before relying on them for reconciliation.</p>
        </section>

        <section className="legal-section">
          <h2>7. Data, exports and backups</h2>
          <p>Your organization remains responsible for its business records and for maintaining any independent records or exports it needs. Do not assume that the service is your only required copy of tax, accounting or other statutory records. Retention, export and deletion may be affected by legal duties, audit requirements, security needs and technical backups.</p>
        </section>

        <section className="legal-section">
          <h2>8. Intellectual property</h2>
          <p>ZenPOS and its interface, software, branding and related materials are owned by or licensed to their respective rights holders. These terms give you a limited, revocable, non-exclusive right to use the service for authorized business purposes. They do not transfer ownership of the platform or its intellectual property to you.</p>
          <p>Your organization retains its rights in the business data it submits, subject to the rights needed to host, process, secure and display that data to provide the service.</p>
        </section>

        <section className="legal-section">
          <h2>9. Suspension and termination</h2>
          <p>Access may be suspended or terminated if an account is compromised, these terms are materially breached, use creates a security or legal risk, or the organization or service provider ends the applicable arrangement. Where reasonable and lawful, notice or an opportunity to remedy a problem may be provided.</p>
          <p>When access ends, your organization should arrange any needed exports promptly. Some records may be retained where required for legal, audit, security or backup purposes.</p>
        </section>

        <section className="legal-section">
          <h2>10. Disclaimers and liability</h2>
          <p>To the extent permitted by applicable law, ZenPOS is provided on an “as available” basis, without a guarantee that it will meet every business requirement or be error-free. Nothing in these terms excludes a warranty, right or liability that cannot lawfully be excluded.</p>
          <p>To the extent permitted by law, the service provider is not liable for indirect or consequential losses arising from use of the service, data-entry errors, third-party outages or a user's failure to keep independent records. This section does not override any liability that applicable law does not permit to be limited.</p>
        </section>

        <section className="legal-section">
          <h2>11. Privacy</h2>
          <p>Use of personal information through ZenPOS is described in our <Link to="/privacy">Privacy Policy</Link>. Organizations and users must handle personal information lawfully and use appropriate access controls.</p>
        </section>

        <section className="legal-section">
          <h2>12. Changes to these terms</h2>
          <p>These terms may be revised when the platform or applicable requirements change. The updated version will be published on this page with a revised date. Continued use after changes take effect indicates acceptance where permitted by law. If you do not agree to a material change, stop using the service and contact your organization administrator about account access.</p>
        </section>

        <section className="legal-section">
          <h2>13. Governing law and contact</h2>
          <p>These terms are intended to operate consistently with the laws of Kenya, subject to any mandatory laws that apply to a particular user or arrangement. If you have questions about your account, contact your organization administrator or the ZenPOS support channel provided when your account was set up.</p>
        </section>

        <p className="legal-note">This page is a general terms template, not legal advice. The service operator should review it against its actual commercial arrangements, pricing, support commitments and liability position before treating it as a final legal agreement.</p>
      </main>
      <SiteFooter />
    </div>
  );
}

export default TermsAndConditions;

import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ShieldCheck } from 'lucide-react';
import Brand from '../components/site/Brand';
import SiteFooter from '../components/site/SiteFooter';
import '../styles/site.css';
import '../styles/legal.css';

function PrivacyPolicy() {
  return (
    <div className="zenpos-site legal-page">
      <header className="legal-header">
        <Brand />
        <Link className="legal-back-link" to="/"><ArrowLeft size={15} /> Back to home</Link>
      </header>
      <main className="legal-main">
        <div className="legal-kicker"><ShieldCheck size={15} /> YOUR INFORMATION</div>
        <h1>Privacy policy</h1>
        <p className="legal-intro">This policy explains how ZenPOS handles information when you use our point-of-sale and retail operations platform.</p>
        <p className="legal-updated">Last updated: 17 October 2026</p>

        <section className="legal-section">
          <h2>1. Scope and roles</h2>
          <p>ZenPOS supports sales, inventory, customer records, staff access, reporting and related retail workflows. Depending on how your account is provided, the shop or organization using ZenPOS may decide why customer and employee information is collected, while the ZenPOS service operator may process that information to provide and maintain the service.</p>
          <p>Your organization remains responsible for providing appropriate notices and having a lawful basis for information it enters into the platform. This policy should be read alongside any privacy notice provided by your employer or business.</p>
        </section>

        <section className="legal-section">
          <h2>2. Information that may be processed</h2>
          <ul>
            <li><strong>Account and staff details:</strong> usernames, account identifiers, assigned roles, permissions and organization or branch associations.</li>
            <li><strong>Business records:</strong> product, stock, purchase, sales, till-session, refund and reporting records entered or generated through the service.</li>
            <li><strong>Customer and supplier details:</strong> names, contact details and other information your organization chooses to record.</li>
            <li><strong>Transaction and compliance details:</strong> payment status or references, tax and eTIMS-related records, where those features are enabled. ZenPOS should not be used to store card PINs, passwords or M-Pesa PINs.</li>
            <li><strong>Technical information:</strong> security events, request metadata, device/browser information and diagnostic logs needed to operate, protect and troubleshoot the service.</li>
          </ul>
          <p>The exact information processed depends on the features enabled and what your organization enters. Do not enter information that is unnecessary for your business workflow.</p>
        </section>

        <section className="legal-section">
          <h2>3. How information is used</h2>
          <p>Information may be used to authenticate users, enforce roles and organization boundaries, record sales and inventory activity, provide reports, support configured payment or tax workflows, maintain audit trails, prevent misuse, troubleshoot faults, and maintain or improve service reliability.</p>
          <p>ZenPOS does not promise that every integration or payment method is available in every account. External providers may process information under their own terms and privacy notices.</p>
        </section>

        <section className="legal-section">
          <h2>4. Sharing and service providers</h2>
          <p>Information may be available to authorized users within your organization according to their assigned permissions. It may also be processed by infrastructure, hosting, database, communications, payment or tax-service providers where needed to deliver enabled features, or disclosed when required by law or necessary to protect the service and its users.</p>
          <p>ZenPOS does not sell personal information as a business model. Access to information should be limited to legitimate operational, security and legal needs.</p>
        </section>

        <section className="legal-section">
          <h2>5. Security and retention</h2>
          <p>Reasonable technical and organizational safeguards are used to protect the service, including account authentication and permission checks. No internet-connected system can be guaranteed completely secure. Keep your login credentials confidential and promptly tell your organization administrator if you suspect unauthorized access.</p>
          <p>Information is retained for as long as reasonably necessary for the business purposes described above, account operation, audit and legal obligations, dispute resolution, and secure backups. Your organization may have separate record-retention obligations for sales, tax and employment records.</p>
        </section>

        <section className="legal-section">
          <h2>6. Your privacy rights</h2>
          <p>Applicable data-protection law may give you rights to request access to, correction of, deletion of, restriction of, or objection to certain uses of your personal data. The availability of a right depends on the circumstances and applicable law; some business, accounting, security or legal records may need to be retained.</p>
          <p>If the information was entered by a shop or employer, contact that organization first. For a request about the ZenPOS service itself, use the support or contact channel supplied with your account. We may need to verify your identity and clarify the request before acting.</p>
        </section>

        <section className="legal-section">
          <h2>7. Processing in Kenya and across borders</h2>
          <p>ZenPOS is designed for retail operations in Kenya. Where the Kenya Data Protection Act, 2019 and applicable regulations apply, information should be handled in accordance with those requirements. Some service providers may process or store data outside Kenya; where applicable, cross-border transfers should be subject to required safeguards.</p>
        </section>

        <section className="legal-section">
          <h2>8. Children</h2>
          <p>ZenPOS is a business operations service and is not designed for children to create independent accounts. Organizations should not enter children's personal information unless it is necessary, lawful and appropriately protected.</p>
        </section>

        <section className="legal-section">
          <h2>9. Changes to this policy</h2>
          <p>This policy may be updated as the service, integrations or legal requirements change. The revised version will be published on this page with an updated date. Material changes should also be communicated through an appropriate channel where required.</p>
        </section>

        <section className="legal-section">
          <h2>10. Contact and complaints</h2>
          <p>For account-specific requests, contact your organization administrator or the ZenPOS support channel provided when your account was set up. You may also have the right to raise a complaint with the relevant data-protection authority, including Kenya's Office of the Data Protection Commissioner, where applicable.</p>
        </section>

        <p className="legal-note">This page is general information and is not legal advice. The organization operating your ZenPOS account should review it for its actual data practices and legal obligations before relying on it as its complete privacy notice.</p>
      </main>
      <SiteFooter />
    </div>
  );
}

export default PrivacyPolicy;

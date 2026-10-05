import type { ReactNode } from "react";
import { Collage, SiteFonts, SiteFooter, SiteHeader } from "@/components/site-chrome";

interface Props {
  title: string;
  updated: string;
  children: ReactNode;
}

/** Privacy / terms: a short sky band with the title, then plain reading text on paper. */
export function LegalLayout({ title, updated, children }: Props) {
  return (
    <div className="landing legal">
      <SiteFonts />
      <SiteHeader>
        <a href="/#download">Download</a>
      </SiteHeader>

      <main>
        <Collage preset="pale" className="legal-head">
          <div className="wrap">
            <h1><span className="strip">{title}</span></h1>
            <p className="paper legal-updated">Last updated {updated}</p>
          </div>
        </Collage>
        <div className="wrap">
          <article className="legal-body">{children}</article>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}

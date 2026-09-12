import type { Metadata } from "next";
import "./globals.css";
import "./design.css";
import "./landing.css";
import "./refinement.css";
import "./release.css";
import "./neuro.css";
import "./footer.css";
import "./dashboard.css";
import "./workspace-theme.css";
// Responsive rules live with the components' shared design tokens in globals.css.
export const metadata: Metadata = {
  title: "NeuroLoop — Every creative decision, considered.",
  description:
    "Explore predicted cortical responses, run controlled creative experiments, and keep the evidence.",
  icons: { icon: { url: "/brand/favicon.svg", type: "image/svg+xml" } },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

"use client";
import Link from "next/link";
import { BackgroundPaths } from "@/components/ui/background-paths";
import { useEffect, useRef, useState } from "react";
import {
  motion,
  useInView,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";

export function PixelLoading({
  label = "Reading evidence",
  variant = "drive",
}: {
  label?: string;
  variant?: "drive" | "orbit" | "dots";
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const timer = setInterval(
      () => setSeconds(Math.floor((performance.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  return (
    <div className={`pixel-loading ${variant}`} role="status">
      <span className="pixel-grid" aria-hidden="true">
        {Array.from({ length: 9 }, (_, i) => (
          <i
            key={i}
            style={{
              animationDelay: `${(variant === "orbit" ? [0, 1, 2, 7, 0, 3, 6, 5, 4][i] : (i % 3) + Math.abs(Math.floor(i / 3) - 1)) * 100}ms`,
            }}
          />
        ))}
      </span>
      <span className="pixel-loading-label">{label}</span>
      <time aria-label={`${seconds} seconds elapsed`}>
        {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
      </time>
    </div>
  );
}

export function MotionFooter() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const visible = useInView(ref, { margin: "100px" });
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end end"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [90, 0]);
  return (
    <footer className="motion-footer" ref={ref} data-visible={visible}>
      <motion.div
        className="footer-curtain"
        aria-hidden="true"
        initial={false}
        animate={{ scaleY: reduce || visible ? 0 : 1 }}
        transition={{ duration: 1.15, ease: [0.22, 1, 0.36, 1] }}
      />
      <div className="footer-orbit" aria-hidden="true" />
      <BackgroundPaths />
      <div className="footer-opening">
        <div>
          <span className="eyebrow">THE NEXT QUESTION IS YOURS.</span>
          <h2>
            Look closer.
            <br />
            <em>Go further.</em>
          </h2>
        </div>
      </div>
      <div className="footer-marquee" aria-hidden="true">
        <div>
          {Array.from({ length: 4 }, (_, i) => (
            <span key={i}>
              QUESTION <i>↗</i> EXPERIMENT <i>↗</i> UNDERSTAND <i>↗</i>{" "}
            </span>
          ))}
        </div>
      </div>
      <div className="footer-links">
        <p>
          A considered process.
          <br />A traceable creative decision.
        </p>
        <nav aria-label="Footer workspace">
          <Link href="/workspace?view=library">Creative library ↗</Link>
          <Link href="/workspace?view=brain">Brain lab ↗</Link>
          <Link href="/workspace?view=research">Research & methodology ↗</Link>
        </nav>
        <nav aria-label="Footer connections">
          <Link href="/neuro">Meet Neuro AI ↗</Link>
          <Link href="/workspace?view=connections">Connect your agent ↗</Link>
          <a href="#top">Back to top ↑</a>
        </nav>
      </div>
      <div className="footer-wordmark-window" aria-hidden="true">
        <motion.div
          className="footer-wordmark"
          style={reduce ? undefined : { y }}
        >
          NeuroLoop
        </motion.div>
      </div>
      <div className="footer-legal">
        <span>© {new Date().getFullYear()} NeuroLoop</span>
        <span>Local research. Actual evidence.</span>
      </div>
    </footer>
  );
}

"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  motion,
  useInView,
  useReducedMotion,
  useScroll,
  useTransform,
  useMotionValue,
  useSpring,
} from "motion/react";
import { ArrowUpRight } from "lucide-react";

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

export function BackgroundPaths() {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const visible = useInView(ref);
  return (
    <div ref={ref} className="background-paths" aria-hidden="true">
      <svg viewBox="0 0 696 316" fill="none">
        {[-1, 1].flatMap((position) =>
          Array.from({ length: 24 }, (_, i) => (
            <motion.path
              key={`${position}-${i}`}
              d={`M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${152 - i * 5 * position} ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 5}`}
              stroke="currentColor"
              strokeWidth={0.6 + i * 0.025}
              initial={false}
              animate={
                reduce || !visible
                  ? { opacity: 0.25 }
                  : {
                      pathLength: [0.35, 1, 0.35],
                      pathOffset: [0, 1, 0],
                      opacity: [0.12, 0.4, 0.12],
                    }
              }
              transition={{
                duration: 22 + i * 0.5,
                repeat: Infinity,
                ease: "linear",
              }}
            />
          )),
        )}
      </svg>
    </div>
  );
}

export function MotionFooter() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const visible = useInView(ref, { margin: "100px" });
  const mx = useMotionValue(0),
    my = useMotionValue(0);
  const x = useSpring(mx, { stiffness: 160, damping: 18 }),
    magneticY = useSpring(my, { stiffness: 160, damping: 18 });
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
        <motion.div
          style={reduce ? undefined : { x, y: magneticY }}
          onPointerMove={(event) => {
            if (reduce || event.pointerType !== "mouse") return;
            const r = event.currentTarget.getBoundingClientRect();
            mx.set((event.clientX - r.left - r.width / 2) * 0.12);
            my.set((event.clientY - r.top - r.height / 2) * 0.12);
          }}
          onPointerLeave={() => {
            mx.set(0);
            my.set(0);
          }}
        >
          <Link className="footer-magnetic" href="/workspace">
            <ArrowUpRight size={38} />
            <span>
              Open your
              <br />
              workspace
            </span>
          </Link>
        </motion.div>
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
          <Link href="/neuro">Meet Neuro ↗</Link>
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

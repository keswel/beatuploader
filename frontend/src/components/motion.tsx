import { motion, type Variants, type HTMLMotionProps } from "motion/react";
import { type ReactNode } from "react";

/** iOS spring — fast, settled, no overshoot */
const spring = [0.32, 0.72, 0, 1] as const;
/** Smooth ease — for distance-based moves */
const smooth = [0.22, 1, 0.36, 1] as const;

export const fadeUpVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: smooth },
  },
};

export const staggerContainer: Variants = {
  hidden: { opacity: 1 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04, delayChildren: 0.04 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: smooth },
  },
};

interface FadeUpProps extends HTMLMotionProps<"div"> {
  delay?: number;
  children: ReactNode;
}

export function FadeUp({ delay = 0, children, ...rest }: FadeUpProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: smooth, delay }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

interface StaggerProps extends HTMLMotionProps<"div"> {
  children: ReactNode;
  stagger?: number;
  delayChildren?: number;
}

export function Stagger({
  children,
  stagger = 0.04,
  delayChildren = 0.04,
  ...rest
}: StaggerProps) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{
        hidden: { opacity: 1 },
        show: {
          opacity: 1,
          transition: { staggerChildren: stagger, delayChildren },
        },
      }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

interface StaggerItemProps extends HTMLMotionProps<"div"> {
  children: ReactNode;
}

export function StaggerItem({ children, ...rest }: StaggerItemProps) {
  return (
    <motion.div variants={staggerItem} {...rest}>
      {children}
    </motion.div>
  );
}

export { motion, spring, smooth };

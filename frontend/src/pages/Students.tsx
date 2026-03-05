import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import {
  Users,
  TrendingUp,
  Presentation,
  Loader2,
  X,
  Target,
  Sparkles,
  Activity,
  Radar,
} from "lucide-react";
import { instructorAPI } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

type RankedStudent = {
  first_name: string;
  total_percent?: number;
  score?: number;
};

type SubjectDetails = {
  top_5?: RankedStudent[];
  bottom_5?: RankedStudent[];
};

type StudentAnalytics = {
  averages?: Record<string, number | string>;
  averages_total?: number | string;
  total_percent_min_max?: {
    max?: number | string;
    min?: number | string;
  };
  total_students?: number;
  top_5?: RankedStudent[];
  bottom_5?: RankedStudent[];
  subject_details?: Record<string, SubjectDetails>;
  total_graded_exams?: number;
};

type SubjectAverage = {
  subject: string;
  rawSubject: string;
  Score: number;
};

function toNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatPercent(value: number, decimals = 2): string {
  return `${Number(value.toFixed(decimals))}%`;
}

function AnimatedNumber({
  value,
  decimals = 0,
  suffix = "",
  className = "",
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  className?: string;
}) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    let frame = 0;
    let start: number | null = null;
    const from = displayValue;
    const to = Number.isFinite(value) ? value : 0;
    const duration = 900;

    const tick = (timestamp: number) => {
      if (start === null) {
        start = timestamp;
      }
      const progress = Math.min((timestamp - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(from + (to - from) * eased);

      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span className={className}>
      {displayValue.toFixed(decimals)}
      {suffix}
    </span>
  );
}

const summaryCardVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.45,
      delay: 0.1 + index * 0.08,
      ease: [0.22, 1, 0.36, 1],
    },
  }),
};

const listItemVariants = {
  hidden: { opacity: 0, x: 10 },
  visible: (index: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      duration: 0.3,
      delay: 0.05 * index,
    },
  }),
};

export function Students() {
  const { user } = useAuth();
  const [analytics, setAnalytics] = useState<StudentAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);

  useEffect(() => {
    const fetchAllData = async () => {
      if (!user) {
        return;
      }
      setLoading(true);
      try {
        const [studentAn, examAn] = await Promise.all([
          instructorAPI.getStudentAnalytics(),
          instructorAPI.getAnalytics(user.id),
        ]);
        setAnalytics({
          ...studentAn,
          total_graded_exams: examAn?.total_graded_submissions || 0,
        });
      } catch (err) {
        console.error("Failed to fetch analytics", err);
      } finally {
        setLoading(false);
      }
    };
    fetchAllData();
  }, [user]);

  const subjectAverages = useMemo<SubjectAverage[]>(() => {
    if (!analytics?.averages) {
      return [];
    }
    return Object.entries(analytics.averages).map(([subject, avg]) => ({
      subject: subject.charAt(0).toUpperCase() + subject.slice(1),
      rawSubject: subject,
      Score: toNumber(avg),
    }));
  }, [analytics]);

  const topSubject = useMemo(() => {
    if (!subjectAverages.length) {
      return null;
    }
    return [...subjectAverages].sort((a, b) => b.Score - a.Score)[0];
  }, [subjectAverages]);

  const bottomSubject = useMemo(() => {
    if (!subjectAverages.length) {
      return null;
    }
    return [...subjectAverages].sort((a, b) => a.Score - b.Score)[0];
  }, [subjectAverages]);

  const overallAverage = toNumber(analytics?.averages_total);
  const highestTotal = toNumber(analytics?.total_percent_min_max?.max);
  const lowestTotal = toNumber(analytics?.total_percent_min_max?.min);
  const totalStudents = toNumber(analytics?.total_students);
  const scoreSpread = Math.max(0, highestTotal - lowestTotal);
  const consistencyScore = Math.max(0, 100 - scoreSpread);
  const topFiveAverage =
    analytics?.top_5?.length
      ? analytics.top_5.reduce((sum, student) => sum + toNumber(student.total_percent), 0) / analytics.top_5.length
      : 0;
  const bottomFiveAverage =
    analytics?.bottom_5?.length
      ? analytics.bottom_5.reduce((sum, student) => sum + toNumber(student.total_percent), 0) / analytics.bottom_5.length
      : 0;

  const barColors = ["#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95", "#8b5cf6"];

  const summaryCards = [
    {
      title: "Overall Average",
      description: "Across all subjects",
      value: overallAverage,
      decimals: 1,
      suffix: "%",
      progress: overallAverage,
      icon: Presentation,
      iconClassName: "text-primary",
      hoverBorderClassName: "hover:border-primary/50",
      progressClassName: "from-violet-500 to-violet-300",
      topLineClassName: "from-violet-500/60 via-violet-400/20 to-transparent",
    },
    {
      title: "Highest total %",
      description: "Top tier performance",
      value: highestTotal,
      decimals: 1,
      suffix: "%",
      progress: highestTotal,
      icon: TrendingUp,
      iconClassName: "text-green-500",
      hoverBorderClassName: "hover:border-green-500/50",
      progressClassName: "from-green-500 to-emerald-300",
      topLineClassName: "from-green-500/60 via-green-400/25 to-transparent",
    },
    {
      title: "Lowest total %",
      description: "Struggling tier",
      value: lowestTotal,
      decimals: 1,
      suffix: "%",
      progress: lowestTotal,
      icon: Target,
      iconClassName: "text-destructive",
      hoverBorderClassName: "hover:border-destructive/50",
      progressClassName: "from-red-500 to-orange-300",
      topLineClassName: "from-red-500/65 via-red-400/25 to-transparent",
    },
    {
      title: "Total students",
      description: "Enrolled students",
      value: totalStudents,
      decimals: 0,
      suffix: "",
      progress: Math.min(100, totalStudents * 2),
      icon: Users,
      iconClassName: "text-amber-500",
      hoverBorderClassName: "hover:border-amber-500/50",
      progressClassName: "from-amber-500 to-yellow-300",
      topLineClassName: "from-amber-500/60 via-amber-400/20 to-transparent",
    },
  ];

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="stats-theme relative max-w-7xl mx-auto space-y-8 pb-20 overflow-hidden">
      <div className="stats-ambient-grid" />
      <motion.div
        className="stats-orb stats-orb-1"
        animate={{ x: [0, 24, 0], y: [0, -16, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="stats-orb stats-orb-2"
        animate={{ x: [0, -28, 0], y: [0, 20, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-semibold text-primary/90">
            <Sparkles className="h-3.5 w-3.5" />
            Cohort intelligence
          </div>
          <h1 className="mt-3 text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary-foreground">
            Student Performance
          </h1>
          <p className="text-muted-foreground mt-2">Comprehensive analytics across subjects and exams.</p>
        </div>

        <motion.div
          className="glass-panel rounded-xl border-border/70 px-4 py-3 min-w-[230px]"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15, duration: 0.35 }}
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Class Snapshot</p>
          <div className="mt-2 grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Consistency</p>
              <p className="text-lg font-semibold text-primary">{formatPercent(consistencyScore, 0)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Spread</p>
              <p className="text-lg font-semibold text-amber-500">{formatPercent(scoreSpread, 1)}</p>
            </div>
          </div>
        </motion.div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((card, index) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.title}
              custom={index}
              variants={summaryCardVariants}
              initial="hidden"
              animate="visible"
              whileHover={{ y: -6 }}
            >
              <Card
                className={[
                  "glass-panel relative overflow-hidden border-border/70 transition-all duration-300",
                  card.hoverBorderClassName,
                ].join(" ")}
              >
                <div className={`absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r ${card.topLineClassName}`} />
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">{card.title}</CardTitle>
                  <Icon className={`h-4 w-4 ${card.iconClassName}`} />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    <AnimatedNumber value={card.value} decimals={card.decimals} suffix={card.suffix} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{card.description}</p>
                  <div className="mt-4 h-1.5 w-full rounded-full bg-foreground/5 overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full bg-gradient-to-r ${card.progressClassName}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.max(0, Math.min(100, card.progress))}%` }}
                      transition={{
                        duration: 0.8,
                        delay: 0.2 + index * 0.08,
                        ease: [0.22, 1, 0.36, 1],
                      }}
                    />
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-8">
        <motion.div
          className="lg:col-span-2 space-y-6 relative"
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.45 }}
        >
          <Card className="glass-panel border-border/70">
            <CardHeader className="space-y-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <div>
                  <CardTitle>Average score by subject</CardTitle>
                  <CardDescription>Click a bar to view top 5 and lowest 5 for that subject.</CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="stats-pill">
                    <Activity className="h-3.5 w-3.5 text-green-500" />
                    Strongest: {topSubject?.subject || "N/A"}
                  </span>
                  <span className="stats-pill">
                    <Radar className="h-3.5 w-3.5 text-amber-500" />
                    Needs focus: {bottomSubject?.subject || "N/A"}
                  </span>
                </div>
              </div>
            </CardHeader>

            <CardContent className="h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={subjectAverages}
                  onClick={(data: any) => {
                    if (data && data.activePayload && data.activePayload.length > 0) {
                      setSelectedSubject(data.activePayload[0].payload.rawSubject);
                    }
                  }}
                >
                  <XAxis dataKey="subject" stroke="#6b5bb6" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="#6b5bb6"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => `${value}%`}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(139, 92, 246, 0.08)" }}
                    contentStyle={{
                      backgroundColor: "rgba(255, 255, 255, 0.97)",
                      border: "1px solid #e0e7ff",
                      borderRadius: "12px",
                      color: "#312e81",
                      boxShadow: "0 10px 30px -18px rgba(15, 23, 42, 0.35)",
                    }}
                  />
                  <Bar
                    dataKey="Score"
                    radius={[8, 8, 0, 0]}
                    maxBarSize={86}
                    className="cursor-pointer"
                    isAnimationActive
                    animationDuration={950}
                    animationEasing="ease-out"
                  >
                    {subjectAverages.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={barColors[index % barColors.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <AnimatePresence>
            {selectedSubject && analytics?.subject_details?.[selectedSubject] && (
              <motion.div
                initial={{ opacity: 0, scale: 0.92, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.92, y: 20 }}
                className="absolute inset-0 z-20 flex items-center justify-center p-4"
              >
                <div
                  className="absolute inset-0 bg-foreground/20 backdrop-blur-sm rounded-xl"
                  onClick={() => setSelectedSubject(null)}
                />
                <Card className="w-full max-w-md bg-card border-border shadow-2xl relative z-30">
                  <CardHeader className="flex flex-row items-center justify-between pb-4 border-b border-border">
                    <CardTitle className="text-lg">{selectedSubject.toUpperCase()} - Top 5 & Lowest 5</CardTitle>
                    <button
                      onClick={() => setSelectedSubject(null)}
                      className="p-1 hover:bg-accent rounded-full transition-colors"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </CardHeader>
                  <CardContent className="pt-6 grid grid-cols-2 gap-8">
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-green-500 text-xs font-bold uppercase tracking-widest">
                        <TrendingUp className="h-3 w-3" /> Top 5
                      </div>
                      <div className="space-y-2">
                        {(analytics.subject_details[selectedSubject].top_5 || []).map((student, i) => (
                          <motion.div
                            key={`${student.first_name}-${i}`}
                            className="flex justify-between items-center text-sm"
                            custom={i}
                            variants={listItemVariants}
                            initial="hidden"
                            animate="visible"
                          >
                            <span className="text-muted-foreground">
                              {i + 1}. {student.first_name}
                            </span>
                            <span className="font-bold">{formatPercent(toNumber(student.score), 1)}</span>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-orange-500 text-xs font-bold uppercase tracking-widest">
                        <Target className="h-3 w-3" /> Lowest 5
                      </div>
                      <div className="space-y-2">
                        {(analytics.subject_details[selectedSubject].bottom_5 || []).map((student, i) => (
                          <motion.div
                            key={`${student.first_name}-${i}`}
                            className="flex justify-between items-center text-sm"
                            custom={i}
                            variants={listItemVariants}
                            initial="hidden"
                            animate="visible"
                          >
                            <span className="text-muted-foreground">
                              {i + 1}. {student.first_name}
                            </span>
                            <span className="font-bold">{formatPercent(toNumber(student.score), 1)}</span>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        <motion.div
          className="space-y-6"
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.45 }}
        >
          <Card className="glass-panel border-border/70">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="h-5 w-5 text-green-500" />
                Top 5 by total %
              </CardTitle>
              <CardDescription>Average of top performers: {formatPercent(topFiveAverage, 2)}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pb-6">
              {analytics?.top_5?.map((student, idx) => {
                const score = toNumber(student.total_percent);
                return (
                  <motion.div
                    key={`${student.first_name}-${idx}`}
                    custom={idx}
                    variants={listItemVariants}
                    initial="hidden"
                    animate="visible"
                    className="text-sm"
                  >
                    <div className="flex items-center justify-between group">
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">{idx + 1}.</span>
                        <span className="font-medium group-hover:text-primary transition-colors">{student.first_name}</span>
                      </div>
                      <span className="font-bold">{formatPercent(score, 2)}</span>
                    </div>
                    <div className="mt-2 h-1.5 w-full rounded-full bg-foreground/5 overflow-hidden">
                      <motion.div
                        className="h-full rounded-full bg-gradient-to-r from-green-500 to-emerald-300"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                        transition={{ duration: 0.6, delay: 0.12 + idx * 0.06 }}
                      />
                    </div>
                  </motion.div>
                );
              })}
              {!analytics?.top_5?.length && <div className="text-sm text-muted-foreground text-center py-4">No data available</div>}
            </CardContent>
          </Card>

          <Card className="glass-panel border-border/70">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Users className="h-5 w-5 text-orange-500" />
                Bottom 5 by total %
              </CardTitle>
              <CardDescription>Average of bottom performers: {formatPercent(bottomFiveAverage, 2)}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pb-6">
              {analytics?.bottom_5?.map((student, idx) => {
                const score = toNumber(student.total_percent);
                return (
                  <motion.div
                    key={`${student.first_name}-${idx}`}
                    custom={idx}
                    variants={listItemVariants}
                    initial="hidden"
                    animate="visible"
                    className="text-sm"
                  >
                    <div className="flex items-center justify-between group">
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">{idx + 1}.</span>
                        <span className="font-medium group-hover:text-destructive transition-colors">{student.first_name}</span>
                      </div>
                      <span className="font-bold">{formatPercent(score, 2)}</span>
                    </div>
                    <div className="mt-2 h-1.5 w-full rounded-full bg-foreground/5 overflow-hidden">
                      <motion.div
                        className="h-full rounded-full bg-gradient-to-r from-red-500 to-orange-300"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                        transition={{ duration: 0.6, delay: 0.12 + idx * 0.06 }}
                      />
                    </div>
                  </motion.div>
                );
              })}
              {!analytics?.bottom_5?.length && (
                <div className="text-sm text-muted-foreground text-center py-4">No data available</div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { BrainCircuit, CheckCircle2, ChevronRight, ChevronLeft, Loader2, Send, AlertTriangle, Camera, ShieldAlert, ShieldCheck, Clock3, Hourglass, AlertCircle } from 'lucide-react';
import { examAPI, proctorAPI, submissionAPI } from '../lib/api';
import type { Exam, ProctorFrameResponse } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../components/ui/card';

export function ExamWindow() {
    const { id } = useParams<{ id: string }>();
    const { user } = useAuth();
    const navigate = useNavigate();

    const [exam, setExam] = useState<Exam | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [answers, setAnswers] = useState<Record<string, string>>({});
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isStartingProctor, setIsStartingProctor] = useState(false);
    const [proctorSessionId, setProctorSessionId] = useState<string | null>(null);
    const [proctorState, setProctorState] = useState<ProctorFrameResponse | null>(null);
    const [proctorError, setProctorError] = useState<string | null>(null);
    const [proctorAlerts, setProctorAlerts] = useState<Array<{ time: string; type: string; message: string; severity: 'high' | 'medium' | 'low' }>>([]);
    const [sessionStartMs, setSessionStartMs] = useState<number | null>(null);
    const [clockNowMs, setClockNowMs] = useState<number>(Date.now());

    // Navigation State
    const [currentSection, setCurrentSection] = useState<'mcq' | 'essay'>('mcq');
    const [currentIndex, setCurrentIndex] = useState(0);
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const intervalRef = useRef<number | null>(null);
    const endingRef = useRef(false);
    const proctorSessionRef = useRef<string | null>(null);
    const isFrameProcessingRef = useRef(false);
    const PROCTOR_DURATION_MINUTES = 60;
    const FRAME_INTERVAL_MS = 500;

    useEffect(() => {
        const fetchExam = async () => {
            if (!id || !user) return;
            try {
                const data = await examAPI.getById(parseInt(id));
                setExam(data);

                // Ensure parsed_content exists or parse it 
                if (!data.parsed_content && data.content) {
                    try {
                        data.parsed_content = JSON.parse(data.content);
                    } catch (e) {
                        console.error("Failed to parse stringified content", e);
                    }
                }
            } catch (err: any) {
                setError(err.response?.data?.detail || "Failed to load exam");
            } finally {
                setLoading(false);
            }
        };

        fetchExam();
    }, [id, user]);

    useEffect(() => {
        const timer = window.setInterval(() => setClockNowMs(Date.now()), 1000);
        return () => window.clearInterval(timer);
    }, []);

    const handleAnswerChange = (questionId: string, answer: string) => {
        setAnswers(prev => ({ ...prev, [questionId]: answer }));
    };

    const stopCamera = () => {
        if (intervalRef.current) {
            window.clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        }
    };

    const endProctoringIfNeeded = async (invalidateReason?: string) => {
        const sessionId = proctorSessionRef.current;
        if (!sessionId || endingRef.current) return;
        endingRef.current = true;
        try {
            await proctorAPI.endSession(sessionId, invalidateReason);
        } catch (err) {
            console.error('Failed to end proctor session', err);
        }
    };

    useEffect(() => {
        return () => {
            stopCamera();
            void endProctoringIfNeeded();
        };
    }, []);

    useEffect(() => {
        const startProctoring = async () => {
            if (!exam || !user || proctorSessionId || isStartingProctor) return;
            setIsStartingProctor(true);
            setProctorError(null);
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
                    audio: false,
                });
                streamRef.current = stream;
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    await videoRef.current.play();
                }

                const session = await proctorAPI.startSession({
                    student_id: user.id,
                    exam_id: exam.id,
                    duration_min: PROCTOR_DURATION_MINUTES,
                    student_name: user.username,
                    exam_title: exam.topic,
                });
                setProctorSessionId(session.session_id);
                proctorSessionRef.current = session.session_id;
                setSessionStartMs(Date.now());
                setProctorAlerts([]);

                intervalRef.current = window.setInterval(async () => {
                    if (!videoRef.current || !canvasRef.current || !session.session_id) return;
                    if (isFrameProcessingRef.current) return;
                    const video = videoRef.current;
                    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
                    const canvas = canvasRef.current;
                    const width = video.videoWidth || 640;
                    const height = video.videoHeight || 480;
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return;
                    ctx.drawImage(video, 0, 0, width, height);
                    const imageBase64 = canvas.toDataURL('image/jpeg', 0.6);
                    isFrameProcessingRef.current = true;
                    try {
                        const frameRes = await proctorAPI.processFrame(session.session_id, imageBase64);
                        setProctorState(frameRes);
                        if (frameRes.alert) {
                            setProctorAlerts((prev) => {
                                const exists = prev.some(
                                    (x) =>
                                        x.time === frameRes.alert!.time &&
                                        x.type === frameRes.alert!.type &&
                                        x.message === frameRes.alert!.message
                                );
                                if (exists) return prev;
                                return [frameRes.alert!, ...prev].slice(0, 150);
                            });
                        }
                        if (frameRes.invalidated) {
                            setProctorError(frameRes.invalidate_reason || 'Exam invalidated by proctoring engine.');
                        }
                    } catch (frameErr: any) {
                        console.error('Frame processing failed', frameErr);
                        const detail = frameErr?.response?.data?.detail;
                        if (typeof detail === 'string') {
                            setProctorError(detail);
                        }
                    } finally {
                        isFrameProcessingRef.current = false;
                    }
                }, FRAME_INTERVAL_MS);
            } catch (err: any) {
                const detail = err?.response?.data?.detail;
                setProctorError(typeof detail === 'string' ? detail : 'Camera/proctoring could not start.');
            } finally {
                setIsStartingProctor(false);
            }
        };

        void startProctoring();
    }, [exam, user, proctorSessionId, isStartingProctor]);

    const handleSubmit = async () => {
        if (!exam || !user) return;

        setIsSubmitting(true);
        try {
            if (proctorState?.invalidated) {
                alert(proctorState.invalidate_reason || 'This exam session was invalidated by proctoring.');
                return;
            }
            await submissionAPI.create({
                exam_id: exam.id,
                student_id: user.id,
                answers: answers,
                proctor_session_id: proctorSessionId,
            });
            await endProctoringIfNeeded();
            stopCamera();
            navigate('/results', { state: { successMessage: 'Exam submitted successfully!' } });
        } catch (err: any) {
            alert(err.response?.data?.detail || "Failed to submit exam");
        } finally {
            setIsSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[70vh] gap-4">
                <Loader2 className="h-10 w-10 animate-spin text-primary" />
                <p className="text-muted-foreground animate-pulse">Initializing Exam Environment...</p>
            </div>
        );
    }

    if (error || !exam) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
                <AlertTriangle className="h-12 w-12 text-destructive" />
                <h2 className="text-2xl font-bold">{error || "Exam not found"}</h2>
                <Button onClick={() => navigate('/')} variant="outline">Return to Dashboard</Button>
            </div>
        );
    }

    const mcqs = exam.parsed_content?.mcqs || exam.parsed_content?.mcq || [];
    const essays = exam.parsed_content?.essays || exam.parsed_content?.essay || [];

    const currentQuestions = currentSection === 'mcq' ? mcqs : essays;
    const q = currentQuestions[currentIndex];

    const handleNext = () => {
        if (currentIndex < currentQuestions.length - 1) {
            setCurrentIndex(prev => prev + 1);
        } else if (currentSection === 'mcq' && essays.length > 0) {
            setCurrentSection('essay');
            setCurrentIndex(0);
        }
    };

    const handlePrev = () => {
        if (currentIndex > 0) {
            setCurrentIndex(prev => prev - 1);
        } else if (currentSection === 'essay' && mcqs.length > 0) {
            setCurrentSection('mcq');
            setCurrentIndex(mcqs.length - 1);
        }
    };

    const isComplete = () => {
        const totalQuestions = mcqs.length + essays.length;
        const answeredCount = Object.keys(answers).length;
        return answeredCount === totalQuestions;
    };

    const progressPercent = ((Object.keys(answers).length) / (mcqs.length + essays.length)) * 100;
    const elapsedSeconds = sessionStartMs ? Math.floor((clockNowMs - sessionStartMs) / 1000) : 0;
    const remainingSeconds = Math.max(0, PROCTOR_DURATION_MINUTES * 60 - elapsedSeconds);
    const formatClock = (value: number) => `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toString().padStart(2, '0')}`;

    return (
        <div className="max-w-4xl mx-auto py-8">
            <canvas ref={canvasRef} className="hidden" />
            {/* Header & Progress */}
            <div className="mb-8 space-y-4">
                <div className="flex justify-between items-end">
                    <div>
                        <h1 className="text-2xl font-bold">{exam.topic}</h1>
                        <p className="text-muted-foreground flex items-center gap-2 mt-1 -ml-1">
                            <span className="text-xs uppercase tracking-wider font-semibold px-2 py-1 rounded-md bg-white/5 border border-white/10">
                                {exam.difficulty}
                            </span>
                            <span>•</span>
                            <span className="text-sm">{mcqs.length} MCQs, {essays.length} Essays</span>
                        </p>
                    </div>
                    {exam.due_at && (
                        <div className="text-right">
                            <span className="text-xs text-muted-foreground uppercase tracking-widest block mb-1">Due By</span>
                            <span className="font-mono text-sm">{new Date(exam.due_at).toLocaleString()}</span>
                        </div>
                    )}
                </div>

                <div className="glass-panel border border-white/10 rounded-xl p-4">
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                        <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                            <p className="text-xs uppercase tracking-wider text-muted-foreground">Focus Score</p>
                            <p className="text-xl font-bold text-cyan-300">{proctorState?.focus_score?.toFixed(1) ?? '100.0'}%</p>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                            <p className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1"><Clock3 className="h-3 w-3" /> Elapsed</p>
                            <p className="text-xl font-bold text-cyan-300">{formatClock(elapsedSeconds)}</p>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                            <p className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1"><Hourglass className="h-3 w-3" /> Remaining</p>
                            <p className="text-xl font-bold text-cyan-300">{formatClock(remainingSeconds)}</p>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                            <p className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1"><AlertCircle className="h-3 w-3" /> Total Alerts</p>
                            <p className="text-xl font-bold text-cyan-300">{proctorState?.total_alerts ?? 0}</p>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                            <p className="text-xs uppercase tracking-wider text-muted-foreground">High Alerts</p>
                            <p className="text-xl font-bold text-cyan-300">{proctorState?.high_alerts ?? 0}</p>
                        </div>
                    </div>
                    <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
                        <div className="space-y-1">
                            <p className="text-sm uppercase tracking-widest text-muted-foreground">AI Proctoring</p>
                            <div className="flex items-center gap-2">
                                {proctorState?.invalidated ? (
                                    <ShieldAlert className="h-5 w-5 text-destructive" />
                                ) : (
                                    <ShieldCheck className="h-5 w-5 text-green-400" />
                                )}
                                <span className="text-sm">
                                    {isStartingProctor
                                        ? 'Starting proctoring...'
                                        : proctorSessionId
                                            ? `Session active (${proctorSessionId.slice(0, 8)}...)`
                                            : 'Session inactive'}
                                </span>
                            </div>
                            {proctorError && <p className="text-xs text-destructive">{proctorError}</p>}
                        </div>
                        <div className="text-sm text-muted-foreground flex gap-4 flex-wrap">
                            <span>Focus: <strong className="text-foreground">{proctorState?.focus_score?.toFixed(1) ?? 'N/A'}%</strong></span>
                            <span>Alerts: <strong className="text-foreground">{proctorState?.total_alerts ?? 0}</strong></span>
                            <span>High: <strong className="text-foreground">{proctorState?.high_alerts ?? 0}</strong></span>
                        </div>
                    </div>
                    <video ref={videoRef} muted playsInline className="mt-3 w-full max-w-xs rounded-lg border border-white/10 bg-black/40" />
                    <div className="mt-2 text-xs text-muted-foreground flex items-center gap-2">
                        <Camera className="h-3.5 w-3.5" />
                        {proctorState?.metrics?.face_detected ? 'Face detected' : 'Face not detected'}
                        {!proctorState?.metrics?.face_detected
                            ? ' - Not focused'
                            : proctorState?.metrics?.looking_away
                                ? ' - Looking away'
                                : ' - Focused'}
                        {proctorState?.metrics?.multi_face ? ' - Multiple faces detected' : ''}
                    </div>

                    <div className="mt-4 rounded-lg border border-white/10 bg-black/20 overflow-hidden">
                        <div className="px-3 py-2 border-b border-white/10 text-sm font-semibold text-amber-300">
                            Alert Log
                        </div>
                        {proctorAlerts.length === 0 ? (
                            <div className="px-3 py-3 text-xs text-muted-foreground">No alerts yet. Keep focusing on screen.</div>
                        ) : (
                            <div className="max-h-44 overflow-y-auto">
                                {proctorAlerts.map((alert, idx) => (
                                    <div key={`${alert.time}-${alert.type}-${idx}`} className="px-3 py-2 border-b border-white/5 text-xs flex items-center gap-3">
                                        <span className="font-mono text-muted-foreground w-20">{new Date(alert.time).toLocaleTimeString()}</span>
                                        <span
                                            className={`inline-block h-3 w-3 rounded-full ${alert.severity === 'high'
                                                ? 'bg-red-400'
                                                : alert.severity === 'medium'
                                                    ? 'bg-yellow-400'
                                                    : 'bg-green-400'
                                                }`}
                                        />
                                        <span className={`${alert.severity === 'high' ? 'text-red-300' : alert.severity === 'medium' ? 'text-yellow-200' : 'text-green-300'}`}>
                                            {alert.message}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="h-2 w-full bg-white/10 rounded-full overflow-hidden">
                    <motion.div
                        className="h-full bg-gradient-to-r from-primary to-cyan-400"
                        initial={{ width: 0 }}
                        animate={{ width: `${progressPercent}%` }}
                        transition={{ duration: 0.5 }}
                    />
                </div>
            </div>

            <AnimatePresence mode="wait">
                {!q ? (
                    <motion.div
                        key="empty"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-center py-20"
                    >
                        No questions available for this exam format.
                    </motion.div>
                ) : (
                    <motion.div
                        key={`${currentSection}-${currentIndex}`}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        transition={{ duration: 0.3 }}
                    >
                        <Card className="glass-panel border-white/10 shadow-2xl relative overflow-hidden min-h-[400px]">
                            <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                                <BrainCircuit className="w-32 h-32" />
                            </div>

                            <CardHeader className="border-b border-white/5 bg-black/20">
                                <div className="flex justify-between items-center">
                                    <span className="text-sm font-semibold tracking-wider text-muted-foreground uppercase">
                                        {currentSection === 'mcq' ? 'Multiple Choice' : 'Essay Response'}
                                        <span className="text-primary ml-2">({currentIndex + 1} of {currentQuestions.length})</span>
                                    </span>

                                    {answers[`${currentSection}_${currentIndex}`] && (
                                        <CheckCircle2 className="h-5 w-5 text-green-400" />
                                    )}
                                </div>
                                <CardTitle className="text-xl md:text-2xl leading-relaxed mt-4 font-normal">
                                    {q.question}
                                </CardTitle>
                            </CardHeader>

                            <CardContent className="pt-8 pb-12">
                                {currentSection === 'mcq' ? (
                                    <div className="space-y-3">
                                        {q.options?.map((opt: string, idx: number) => {
                                            const ansKey = `${currentSection}_${currentIndex}`;
                                            const isSelected = answers[ansKey] === opt;
                                            return (
                                                <label
                                                    key={idx}
                                                    className={`flex items-center gap-4 p-4 rounded-xl border transition-all cursor-pointer ${isSelected
                                                        ? 'bg-primary/20 border-primary/50 text-white'
                                                        : 'bg-black/40 border-white/10 text-muted-foreground hover:bg-white/5'
                                                        }`}
                                                >
                                                    <input
                                                        type="radio"
                                                        name={`question-${currentIndex}`}
                                                        className="hidden"
                                                        checked={isSelected}
                                                        onChange={() => handleAnswerChange(ansKey, opt)}
                                                    />
                                                    <div className={`h-5 w-5 rounded-full border flex items-center justify-center shrink-0 ${isSelected ? 'border-primary bg-primary' : 'border-white/30'
                                                        }`}>
                                                        {isSelected && <div className="h-2 w-2 rounded-full bg-white" />}
                                                    </div>
                                                    <span className={`${isSelected ? 'font-medium' : ''}`}>{opt}</span>
                                                </label>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <div className="space-y-4">
                                        <Label htmlFor="essay_answer" className="text-muted-foreground ml-1">Your Detailed Answer</Label>
                                        <Textarea
                                            id="essay_answer"
                                            className="min-h-[250px] bg-black/40 border-white/10 focus:border-primary/50 text-base resize-none"
                                            placeholder="Type your response here..."
                                            value={answers[`${currentSection}_${currentIndex}`] || ''}
                                            onChange={(e) => handleAnswerChange(`${currentSection}_${currentIndex}`, e.target.value)}
                                        />
                                    </div>
                                )}
                            </CardContent>

                            <CardFooter className="flex justify-between border-t border-white/5 pt-6 bg-black/20">
                                <Button
                                    variant="outline"
                                    onClick={handlePrev}
                                    disabled={currentSection === 'mcq' && currentIndex === 0}
                                    className="bg-black/50 border-white/10 hover:bg-white/10"
                                >
                                    <ChevronLeft className="mr-2 h-4 w-4" /> Previous
                                </Button>

                                {(currentSection === 'essay' && currentIndex === essays.length - 1) ||
                                    (currentSection === 'mcq' && essays.length === 0 && currentIndex === mcqs.length - 1) ? (
                                    <Button
                                        onClick={handleSubmit}
                                        disabled={isSubmitting || !isComplete() || !!proctorState?.invalidated}
                                        className={`bg-green-600 hover:bg-green-700 text-white px-8 ${isComplete() ? 'animate-pulse' : 'opacity-50'}`}
                                    >
                                        {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                                        Submit Exam
                                    </Button>
                                ) : (
                                    <Button onClick={handleNext} className="bg-primary hover:bg-primary/90 text-white px-8 shadow-lg shadow-primary/20">
                                        Next <ChevronRight className="ml-2 h-4 w-4" />
                                    </Button>
                                )}
                            </CardFooter>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

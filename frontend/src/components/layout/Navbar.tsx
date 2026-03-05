import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../ui/button";
import {
  BrainCircuit,
  FileText,
  ClipboardList,
  BarChart3,
  Bot,
  Home,
  Trophy,
  LogOut,
  User as UserIcon,
} from "lucide-react";

import { AnimatedText } from "../ui/animated-underline-text-one";
import { NavBar, type NavItem } from "../ui/tubelight-navbar";

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate("/auth");
  };

  const instructorItems: NavItem[] = [
    { name: "Generate Exam", url: "/exams", icon: FileText },
    { name: "Manage Exams", url: "/grading", icon: ClipboardList },
    { name: "Insights", url: "/students", icon: BarChart3 },
    { name: "Ask Model", url: "/insights", icon: Bot },
  ];

  const studentItems: NavItem[] = [
    { name: "My Exams", url: "/", icon: Home },
    { name: "Results", url: "/results", icon: Trophy },
  ];

  const navItems = user
    ? user.role === "instructor"
      ? instructorItems
      : studentItems
    : [];

  return (
    <>
      <div className="fixed top-4 left-4 z-50">
        <Link
          to={user?.role === "instructor" ? "/exams" : "/"}
          className="flex items-center gap-2 px-3 py-2 rounded-full glass-panel border border-white/10 transition-transform hover:scale-105"
        >
          <BrainCircuit className="h-5 w-5 text-primary" />
          <AnimatedText
            text="EduGen"
            className="gap-0"
            textClassName="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-cyan-400 leading-none"
            underlineClassName="text-primary/80 -bottom-3"
            underlineDuration={1}
          />
        </Link>
      </div>

      {navItems.length > 0 && (
        <NavBar
          items={navItems}
          activePath={location.pathname}
          className="bottom-0 sm:top-0"
        />
      )}

      <div className="fixed top-4 right-4 z-50 flex items-center gap-2">
        {user ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-full glass-panel border border-white/10">
            <span className="text-sm text-muted-foreground hidden sm:flex items-center gap-2">
              <UserIcon className="h-4 w-4" />
              {user.username}
            </span>
            <Button variant="ghost" size="icon" onClick={handleLogout} title="Log out">
              <LogOut className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        ) : (
          <Button asChild className="bg-primary/90 hover:bg-primary shadow-lg shadow-primary/20">
            <Link to="/auth">Sign In</Link>
          </Button>
        )}
      </div>
    </>
  );
}

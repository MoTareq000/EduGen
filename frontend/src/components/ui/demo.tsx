import { AnimatedText } from "@/components/ui/animated-underline-text-one";
import { Home, User, Briefcase, FileText } from "lucide-react";
import { NavBar } from "@/components/ui/tubelight-navbar";

function DefaultDemo() {
  return <AnimatedText text="Namaste World!" />;
}

function CustomStyleDemo() {
  return (
    <AnimatedText
      text="Namaste World!"
      textClassName="text-5xl font-bold mb-2"
      underlinePath="M 0,10 Q 75,0 150,10 Q 225,20 300,10"
      underlineHoverPath="M 0,10 Q 75,20 150,10 Q 225,0 300,10"
      underlineDuration={1.5}
    />
  );
}

function NavBarDemo() {
  const navItems = [
    { name: "Home", url: "/", icon: Home },
    { name: "About", url: "/about", icon: User },
    { name: "Projects", url: "/projects", icon: Briefcase },
    { name: "Resume", url: "/resume", icon: FileText },
  ];

  return <NavBar items={navItems} />;
}

export { DefaultDemo, CustomStyleDemo, NavBarDemo };

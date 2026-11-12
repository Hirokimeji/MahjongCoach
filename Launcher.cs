using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Launcher {
    [STAThread]
    static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        string script = Path.Combine(root, "MahjongCoach", "boot.py");
        if (!File.Exists(python) || !File.Exists(script)) {
            MessageBox.Show("请先完整解压发行包，再运行此程序。", "雀魂新手教练");
            return;
        }
        try {
            var start = new ProcessStartInfo(python, "-X utf8 \"" + script + "\"");
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
        } catch (Exception error) {
            MessageBox.Show(error.Message, "启动失败");
        }
    }
}

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

type Checks struct {
	DiskEncrypted          bool `json:"disk_encrypted"`
	OSUpToDate             bool `json:"os_up_to_date"`
	AntivirusPresent       bool `json:"antivirus_present"`
	InactivitySleepMinutes int  `json:"inactivity_sleep_minutes"`
}

type SystemData struct {
	MachineID   string `json:"machine_id"`
	MachineName string `json:"machine_name"`
	OS          string `json:"os"`
	OSVersion   string `json:"os_version"`
	Checks      Checks `json:"checks"`
}

func getMachineID() string {
	ifaces, err := net.Interfaces()
	if err == nil {
		for _, iface := range ifaces {
			if len(iface.HardwareAddr) > 0 {
				return iface.HardwareAddr.String()
			}
		}
	}
	// fallback to hostname
	name, _ := os.Hostname()
	return name
}

func getMachineName() string {
	name, err := os.Hostname()
	if err != nil {
		return "unknown-machine"
	}
	return name
}

func checkDiskEncryption() bool {
	switch runtime.GOOS {
	case "darwin":
		out, _ := exec.Command("fdesetup", "status").Output()
		return bytes.Contains(out, []byte("On"))
	case "windows":
		out, _ := exec.Command("manage-bde", "-status").Output()
		return bytes.Contains(out, []byte("Percentage Encrypted"))
	case "linux":
		luksCheck, _ := exec.Command("bash", "-c", "lsblk -o NAME,MOUNTPOINT | grep ' /$' | awk '{print $1}' | xargs -I{} sudo cryptsetup status {}").Output()
		return bytes.Contains(luksCheck, []byte("is active"))
	}
	return false
}

func checkOSUpdateStatus() bool {
	switch runtime.GOOS {
	case "darwin":
		out, _ := exec.Command("softwareupdate", "-l").Output()
		return bytes.Contains(out, []byte("No new software available"))
	case "windows":
		psCmd := `powershell -Command "(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search('IsInstalled=0').Updates.Count"`
		out, _ := exec.Command("cmd", "/C", psCmd).Output()
		return strings.TrimSpace(string(out)) == "0"
	case "linux":
		out, _ := exec.Command("bash", "-c", "apt list --upgradable 2>/dev/null | grep -v Listing | wc -l").Output()
		return strings.TrimSpace(string(out)) == "0"
	}
	return false
}

func checkAntivirus() bool {
	switch runtime.GOOS {
	case "darwin":
		_, err := os.Stat("/System/Library/CoreServices/XProtect.app")
		return err == nil
	case "windows":
		psCmd := `powershell -Command "Get-MpComputerStatus | Select-Object -ExpandProperty AMServiceEnabled"`
		out, _ := exec.Command("cmd", "/C", psCmd).Output()
		return strings.TrimSpace(string(out)) == "True"
	case "linux":
		_, err := exec.LookPath("clamscan")
		return err == nil
	}
	return false
}

func checkSleepMinutes() int {
	switch runtime.GOOS {
	case "darwin":
		out, _ := exec.Command("pmset", "-g", "custom").Output()
		if idx := bytes.Index(out, []byte(" sleep")); idx != -1 {
			var sleepVal int
			fmt.Sscanf(string(out[idx:]), " sleep\t%d", &sleepVal)
			return sleepVal
		}
	case "windows":
		psCmd := `powershell -Command "(Get-ItemProperty -Path 'HKCU:\\Control Panel\\PowerCfg').ScreenSaveTimeOut"`
		out, _ := exec.Command("cmd", "/C", psCmd).Output()
		var secs int
		fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &secs)
		return secs / 60
	case "linux":
		out, _ := exec.Command("gsettings", "get", "org.gnome.desktop.session", "idle-delay").Output()
		var seconds int
		fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &seconds)
		return seconds / 60
	}
	return 0
}

func getOSNameAndVersion() (string, string) {
	switch runtime.GOOS {
	case "darwin":
		nameOut, _ := exec.Command("sw_vers", "-productName").Output()
		verOut, _ := exec.Command("sw_vers", "-productVersion").Output()
		return strings.TrimSpace(string(nameOut)), strings.TrimSpace(string(verOut))
	case "linux":
		out, _ := exec.Command("bash", "-c", "grep PRETTY_NAME /etc/*release | cut -d '\"' -f2").Output()
		parts := strings.SplitN(strings.TrimSpace(string(out)), " ", 2)
		if len(parts) == 2 {
			return parts[0], parts[1]
		}
		return strings.TrimSpace(string(out)), ""
	case "windows":
		out, _ := exec.Command("cmd", "/C", "wmic os get Caption").Output()
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		if len(lines) > 1 {
			full := strings.TrimSpace(lines[1])
			parts := strings.SplitN(full, " ", 2)
			if len(parts) == 2 {
				return parts[0], parts[1]
			}
			return full, ""
		}
		return "Windows", ""
	}
	return "Unknown", ""
}

func collectSystemData() SystemData {
	osName, osVer := getOSNameAndVersion()
	return SystemData{
		MachineID:   getMachineID(),
		MachineName: getMachineName(),
		OS:          osName,
		OSVersion:   osVer,
		Checks: Checks{
			DiskEncrypted:          checkDiskEncryption(),
			OSUpToDate:             checkOSUpdateStatus(),
			AntivirusPresent:       checkAntivirus(),
			InactivitySleepMinutes: checkSleepMinutes(),
		},
	}
}

func displaySystemData(data SystemData) {
	fmt.Println("=== System Health Data ===")
	fmt.Printf("Machine Name: %s\n", data.MachineName)
	fmt.Printf("Machine ID: %s\n", data.MachineID)
	fmt.Printf("Operating System: %s %s\n", data.OS, data.OSVersion)
	fmt.Printf("Disk Encrypted: %v\n", data.Checks.DiskEncrypted)
	fmt.Printf("OS Up-to-date: %v\n", data.Checks.OSUpToDate)
	fmt.Printf("Antivirus Present: %v\n", data.Checks.AntivirusPresent)
	fmt.Printf("Sleep Timeout (mins): %d\n", data.Checks.InactivitySleepMinutes)
	fmt.Println("==========================")
}

func sendData(data SystemData) {
	jsonData, _ := json.Marshal(data)
	resp, err := http.Post("http://192.168.128.116:5000/report", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		fmt.Println("Error sending data:", err)
		return
	}
	defer resp.Body.Close()
	fmt.Println("Data sent, status:", resp.Status)
}

func main() {
	for {
		data := collectSystemData()
		displaySystemData(data)
		sendData(data)
		time.Sleep(30 * time.Minute)
	}
}

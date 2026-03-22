; trevo Windows Installer Script — Inno Setup
; Download Inno Setup from: https://jrsoftware.org/isdl.php
;
; To build: open this file in Inno Setup Compiler and click "Compile"
; Or from command line: iscc installer.iss

#define AppName "trevo"
#define AppVersion "1.0.0"
#define AppPublisher "trevo"
#define AppURL "https://github.com/sidhanthbibi/trevo"
#define AppExeName "trevo.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer_output
OutputBaseFilename=trevo-setup-{#AppVersion}
SetupIconFile=ui\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Launch trevo when Windows starts"; GroupDescription: "Startup:"

[Files]
; Main executable (built by PyInstaller)
Source: "dist\trevo.exe"; DestDir: "{app}"; Flags: ignoreversion

; Assets
Source: "ui\assets\*"; DestDir: "{app}\ui\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; NOTE: config.toml is generated dynamically by [Code] section — not copied from a template

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Auto-start with Windows (optional task)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "trevo"; ValueData: """{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Launch the app after install — no config editing needed
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: postinstall nowait skipifsilent

[Code]
// ============================================================
//  Custom wizard pages for one-click API key setup
// ============================================================

var
  // Speech engine page
  SpeechEnginePage: TWizardPage;
  SpeechEngineCombo: TNewComboBox;
  SpeechEngineDescLabel: TNewStaticText;

  // Polishing provider page
  PolishProviderPage: TWizardPage;
  PolishProviderCombo: TNewComboBox;
  PolishProviderDescLabel: TNewStaticText;

  // API keys page
  APIKeysPage: TWizardPage;
  GroqKeyEdit: TNewEdit;
  GeminiKeyEdit: TNewEdit;
  DeepgramKeyEdit: TNewEdit;
  OpenAIKeyEdit: TNewEdit;
  AnthropicKeyEdit: TNewEdit;

  // Memory Vault page
  VaultPage: TWizardPage;
  VaultDirEdit: TNewEdit;
  VaultBrowseButton: TNewButton;

// ---- Helper: map combo index to engine string ----
function GetSpeechEngineValue(): string;
begin
  case SpeechEngineCombo.ItemIndex of
    0: Result := 'groq';
    1: Result := 'deepgram';
    2: Result := 'whisper_local';
    3: Result := 'openai';
  else
    Result := 'groq';
  end;
end;

function GetPolishProviderValue(): string;
begin
  case PolishProviderCombo.ItemIndex of
    0: Result := 'groq';
    1: Result := 'gemini';
    2: Result := 'ollama';
    3: Result := 'openai';
    4: Result := 'anthropic';
  else
    Result := 'groq';
  end;
end;

// ---- Speech engine description updater ----
procedure SpeechEngineChanged(Sender: TObject);
begin
  case SpeechEngineCombo.ItemIndex of
    0: SpeechEngineDescLabel.Caption :=
         'Groq (Recommended) - Free tier: 30 requests/min.'#13#10 +
         'Fast cloud-based transcription powered by Whisper.'#13#10 +
         'Sign up at: https://console.groq.com';
    1: SpeechEngineDescLabel.Caption :=
         'Deepgram - Paid service with excellent accuracy.'#13#10 +
         'Real-time streaming with interim results.'#13#10 +
         'Sign up at: https://console.deepgram.com';
    2: SpeechEngineDescLabel.Caption :=
         'Whisper Local - Runs entirely on your machine.'#13#10 +
         'No API key needed. Requires ~1-4 GB RAM.'#13#10 +
         'Slower than cloud options but fully private.';
    3: SpeechEngineDescLabel.Caption :=
         'OpenAI Whisper API - Paid, high quality.'#13#10 +
         'Requires an OpenAI API key with billing enabled.'#13#10 +
         'Sign up at: https://platform.openai.com';
  end;
end;

// ---- Polishing provider description updater ----
procedure PolishProviderChanged(Sender: TObject);
begin
  case PolishProviderCombo.ItemIndex of
    0: PolishProviderDescLabel.Caption :=
         'Groq (Recommended) - Free tier: 30 requests/min.'#13#10 +
         'Ultra-fast AI text polishing.'#13#10 +
         'Sign up at: https://console.groq.com';
    1: PolishProviderDescLabel.Caption :=
         'Gemini (Free) - Google AI, 15 requests/min free tier.'#13#10 +
         'Good quality text polishing.'#13#10 +
         'Get key at: https://aistudio.google.com/apikey';
    2: PolishProviderDescLabel.Caption :=
         'Ollama (Local) - Runs on your machine, fully offline.'#13#10 +
         'No API key needed. Install Ollama first: https://ollama.com'#13#10 +
         'Then run: ollama pull llama3.2';
    3: PolishProviderDescLabel.Caption :=
         'OpenAI - Paid, high quality text polishing.'#13#10 +
         'Requires an OpenAI API key with billing.'#13#10 +
         'Sign up at: https://platform.openai.com';
    4: PolishProviderDescLabel.Caption :=
         'Anthropic Claude - Paid, excellent quality.'#13#10 +
         'Requires an Anthropic API key.'#13#10 +
         'Sign up at: https://console.anthropic.com';
  end;
end;

// ---- Browse for vault folder ----
procedure BrowseVaultFolder(Sender: TObject);
var
  Dir: string;
begin
  Dir := VaultDirEdit.Text;
  if BrowseForFolder('Select Memory Vault folder:', Dir, False) then
    VaultDirEdit.Text := Dir;
end;

// ---- Create custom wizard pages ----
procedure InitializeWizard();
var
  L: TNewStaticText;
  TopPos: Integer;
begin
  // ==========================================================
  //  PAGE 1: Speech Engine Selection
  // ==========================================================
  SpeechEnginePage := CreateCustomPage(
    wpSelectTasks,
    'Speech Recognition Engine',
    'Choose how trevo converts your voice to text.'
  );

  L := TNewStaticText.Create(SpeechEnginePage);
  L.Parent := SpeechEnginePage.Surface;
  L.Caption := 'Which speech engine would you like to use?';
  L.Top := 0;
  L.Left := 0;
  L.Font.Style := [fsBold];

  SpeechEngineCombo := TNewComboBox.Create(SpeechEnginePage);
  SpeechEngineCombo.Parent := SpeechEnginePage.Surface;
  SpeechEngineCombo.Top := 28;
  SpeechEngineCombo.Left := 0;
  SpeechEngineCombo.Width := 350;
  SpeechEngineCombo.Style := csDropDownList;
  SpeechEngineCombo.Items.Add('Groq  (Free — Recommended)');
  SpeechEngineCombo.Items.Add('Deepgram  (Paid — Streaming)');
  SpeechEngineCombo.Items.Add('Whisper Local  (Free — Offline)');
  SpeechEngineCombo.Items.Add('OpenAI Whisper API  (Paid)');
  SpeechEngineCombo.ItemIndex := 0;
  SpeechEngineCombo.OnChange := @SpeechEngineChanged;

  SpeechEngineDescLabel := TNewStaticText.Create(SpeechEnginePage);
  SpeechEngineDescLabel.Parent := SpeechEnginePage.Surface;
  SpeechEngineDescLabel.Top := 64;
  SpeechEngineDescLabel.Left := 0;
  SpeechEngineDescLabel.Width := SpeechEnginePage.SurfaceWidth;
  SpeechEngineDescLabel.AutoSize := True;
  SpeechEngineDescLabel.WordWrap := True;
  SpeechEngineDescLabel.Font.Color := clGray;
  // Set initial description
  SpeechEngineChanged(nil);

  // ==========================================================
  //  PAGE 2: Polishing Provider Selection
  // ==========================================================
  PolishProviderPage := CreateCustomPage(
    SpeechEnginePage.ID,
    'AI Text Polishing',
    'Choose which AI cleans up grammar, punctuation, and formatting.'
  );

  L := TNewStaticText.Create(PolishProviderPage);
  L.Parent := PolishProviderPage.Surface;
  L.Caption := 'Which AI provider should polish your text?';
  L.Top := 0;
  L.Left := 0;
  L.Font.Style := [fsBold];

  PolishProviderCombo := TNewComboBox.Create(PolishProviderPage);
  PolishProviderCombo.Parent := PolishProviderPage.Surface;
  PolishProviderCombo.Top := 28;
  PolishProviderCombo.Left := 0;
  PolishProviderCombo.Width := 350;
  PolishProviderCombo.Style := csDropDownList;
  PolishProviderCombo.Items.Add('Groq  (Free — Recommended)');
  PolishProviderCombo.Items.Add('Gemini  (Free — Google AI)');
  PolishProviderCombo.Items.Add('Ollama  (Free — Local / Offline)');
  PolishProviderCombo.Items.Add('OpenAI  (Paid)');
  PolishProviderCombo.Items.Add('Anthropic Claude  (Paid)');
  PolishProviderCombo.ItemIndex := 0;
  PolishProviderCombo.OnChange := @PolishProviderChanged;

  PolishProviderDescLabel := TNewStaticText.Create(PolishProviderPage);
  PolishProviderDescLabel.Parent := PolishProviderPage.Surface;
  PolishProviderDescLabel.Top := 64;
  PolishProviderDescLabel.Left := 0;
  PolishProviderDescLabel.Width := PolishProviderPage.SurfaceWidth;
  PolishProviderDescLabel.AutoSize := True;
  PolishProviderDescLabel.WordWrap := True;
  PolishProviderDescLabel.Font.Color := clGray;
  PolishProviderChanged(nil);

  // ==========================================================
  //  PAGE 3: API Keys
  // ==========================================================
  APIKeysPage := CreateCustomPage(
    PolishProviderPage.ID,
    'API Keys',
    'Enter your API keys below. You can always change these later in Settings.'
  );

  TopPos := 0;

  // --- Groq (primary, prominent) ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'Groq API Key  (Free — https://console.groq.com)';
  L.Top := TopPos;
  L.Left := 0;
  L.Font.Style := [fsBold];
  L.Font.Color := clGreen;
  TopPos := TopPos + 20;

  GroqKeyEdit := TNewEdit.Create(APIKeysPage);
  GroqKeyEdit.Parent := APIKeysPage.Surface;
  GroqKeyEdit.Top := TopPos;
  GroqKeyEdit.Left := 0;
  GroqKeyEdit.Width := APIKeysPage.SurfaceWidth;
  GroqKeyEdit.Text := '';
  TopPos := TopPos + 36;

  // --- Gemini (optional) ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'Gemini API Key  (Optional — https://aistudio.google.com/apikey)';
  L.Top := TopPos;
  L.Left := 0;
  TopPos := TopPos + 20;

  GeminiKeyEdit := TNewEdit.Create(APIKeysPage);
  GeminiKeyEdit.Parent := APIKeysPage.Surface;
  GeminiKeyEdit.Top := TopPos;
  GeminiKeyEdit.Left := 0;
  GeminiKeyEdit.Width := APIKeysPage.SurfaceWidth;
  GeminiKeyEdit.Text := '';
  TopPos := TopPos + 36;

  // --- Deepgram (optional) ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'Deepgram API Key  (Optional — https://console.deepgram.com)';
  L.Top := TopPos;
  L.Left := 0;
  TopPos := TopPos + 20;

  DeepgramKeyEdit := TNewEdit.Create(APIKeysPage);
  DeepgramKeyEdit.Parent := APIKeysPage.Surface;
  DeepgramKeyEdit.Top := TopPos;
  DeepgramKeyEdit.Left := 0;
  DeepgramKeyEdit.Width := APIKeysPage.SurfaceWidth;
  DeepgramKeyEdit.Text := '';
  TopPos := TopPos + 36;

  // --- OpenAI (optional) ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'OpenAI API Key  (Optional — https://platform.openai.com)';
  L.Top := TopPos;
  L.Left := 0;
  TopPos := TopPos + 20;

  OpenAIKeyEdit := TNewEdit.Create(APIKeysPage);
  OpenAIKeyEdit.Parent := APIKeysPage.Surface;
  OpenAIKeyEdit.Top := TopPos;
  OpenAIKeyEdit.Left := 0;
  OpenAIKeyEdit.Width := APIKeysPage.SurfaceWidth;
  OpenAIKeyEdit.Text := '';
  TopPos := TopPos + 36;

  // --- Anthropic (optional) ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'Anthropic API Key  (Optional — https://console.anthropic.com)';
  L.Top := TopPos;
  L.Left := 0;
  TopPos := TopPos + 20;

  AnthropicKeyEdit := TNewEdit.Create(APIKeysPage);
  AnthropicKeyEdit.Parent := APIKeysPage.Surface;
  AnthropicKeyEdit.Top := TopPos;
  AnthropicKeyEdit.Left := 0;
  AnthropicKeyEdit.Width := APIKeysPage.SurfaceWidth;
  AnthropicKeyEdit.Text := '';
  TopPos := TopPos + 36;

  // --- Test Connection note ---
  L := TNewStaticText.Create(APIKeysPage);
  L.Parent := APIKeysPage.Surface;
  L.Caption := 'You can test your API connections after install from Settings.';
  L.Top := TopPos;
  L.Left := 0;
  L.Font.Color := clGray;
  L.Font.Style := [fsItalic];

  // ==========================================================
  //  PAGE 4: Memory Vault
  // ==========================================================
  VaultPage := CreateCustomPage(
    APIKeysPage.ID,
    'Memory Vault',
    'Choose where trevo stores your voice notes, transcripts, and knowledge files.'
  );

  L := TNewStaticText.Create(VaultPage);
  L.Parent := VaultPage.Surface;
  L.Caption :=
    'The Memory Vault is a folder of standard .md (Markdown) files.'#13#10 +
    'It is fully compatible with Obsidian and other Markdown editors.';
  L.Top := 0;
  L.Left := 0;
  L.Width := VaultPage.SurfaceWidth;
  L.AutoSize := True;
  L.WordWrap := True;
  L.Font.Color := clGray;

  L := TNewStaticText.Create(VaultPage);
  L.Parent := VaultPage.Surface;
  L.Caption := 'Vault location:';
  L.Top := 48;
  L.Left := 0;
  L.Font.Style := [fsBold];

  VaultDirEdit := TNewEdit.Create(VaultPage);
  VaultDirEdit.Parent := VaultPage.Surface;
  VaultDirEdit.Top := 68;
  VaultDirEdit.Left := 0;
  VaultDirEdit.Width := VaultPage.SurfaceWidth - 100;
  VaultDirEdit.Text := ExpandConstant('{userprofile}\trevo-vault');

  VaultBrowseButton := TNewButton.Create(VaultPage);
  VaultBrowseButton.Parent := VaultPage.Surface;
  VaultBrowseButton.Caption := 'Browse...';
  VaultBrowseButton.Top := 66;
  VaultBrowseButton.Left := VaultDirEdit.Width + 8;
  VaultBrowseButton.Width := 85;
  VaultBrowseButton.Height := 25;
  VaultBrowseButton.OnClick := @BrowseVaultFolder;
end;

// ---- Write config.toml with user's choices baked in ----
procedure WriteConfigToml();
var
  ConfigPath: string;
  Lines: TStringList;
  Engine, Provider: string;
begin
  ConfigPath := ExpandConstant('{app}\config.toml');
  Engine := GetSpeechEngineValue();
  Provider := GetPolishProviderValue();

  Lines := TStringList.Create;
  try
    Lines.Add('[general]');
    Lines.Add('hotkey = "ctrl+shift+space"');
    Lines.Add('command_hotkey = "ctrl+shift+c"');
    Lines.Add('mode = "toggle"');
    Lines.Add('auto_start = false');
    Lines.Add('start_minimized = true');
    Lines.Add('theme = "dark"');
    Lines.Add('');

    Lines.Add('[stt]');
    Lines.Add('engine = "' + Engine + '"');
    Lines.Add('language = "auto"');
    Lines.Add('deepgram_api_key = "' + DeepgramKeyEdit.Text + '"');
    Lines.Add('openai_api_key = "' + OpenAIKeyEdit.Text + '"');
    Lines.Add('groq_api_key = "' + GroqKeyEdit.Text + '"');
    Lines.Add('gemini_api_key = "' + GeminiKeyEdit.Text + '"');
    Lines.Add('google_cloud_api_key = ""');
    Lines.Add('');

    Lines.Add('[stt.deepgram]');
    Lines.Add('model = "nova-3"');
    Lines.Add('smart_format = true');
    Lines.Add('interim_results = true');
    Lines.Add('filler_words = false');
    Lines.Add('');

    Lines.Add('[stt.whisper]');
    Lines.Add('model_size = "small"');
    Lines.Add('device = "auto"');
    Lines.Add('compute_type = "int8"');
    Lines.Add('');

    Lines.Add('[polishing]');
    Lines.Add('enabled = true');
    Lines.Add('provider = "' + Provider + '"');
    Lines.Add('openai_api_key = "' + OpenAIKeyEdit.Text + '"');
    Lines.Add('anthropic_api_key = "' + AnthropicKeyEdit.Text + '"');
    Lines.Add('groq_api_key = "' + GroqKeyEdit.Text + '"');
    Lines.Add('gemini_api_key = "' + GeminiKeyEdit.Text + '"');
    Lines.Add('ollama_model = "llama3.2"');
    Lines.Add('ollama_url = "http://localhost:11434"');
    Lines.Add('context_aware = true');
    Lines.Add('');

    Lines.Add('[audio]');
    Lines.Add('input_device = "default"');
    Lines.Add('sample_rate = 16000');
    Lines.Add('noise_gate_threshold = 0.01');
    Lines.Add('vad_sensitivity = 0.5');
    Lines.Add('save_audio = false');
    Lines.Add('');

    Lines.Add('[ui]');
    Lines.Add('bar_position = "top_center"');
    Lines.Add('bar_opacity = 0.95');
    Lines.Add('show_interim_results = true');
    Lines.Add('font_size = 14');
    Lines.Add('notification_sounds = true');
    Lines.Add('');

    Lines.Add('[history]');
    Lines.Add('enabled = true');
    Lines.Add('max_entries = 10000');
    Lines.Add('auto_cleanup_days = 90');
    Lines.Add('');

    Lines.Add('[snippets]');
    Lines.Add('');

    Lines.Add('[knowledge]');
    Lines.Add('vault_path = "' + VaultDirEdit.Text + '"');

    Lines.SaveToFile(ConfigPath);
  finally
    Lines.Free;
  end;
end;

// ---- Generate config.toml after files are installed ----
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteConfigToml();
  end;
end;

// ---- Validate: warn if no API key for cloud engines ----
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Engine, Provider: string;
begin
  Result := True;

  if CurPageID = APIKeysPage.ID then
  begin
    Engine := GetSpeechEngineValue();
    Provider := GetPolishProviderValue();

    // Check if user picked a cloud STT engine but gave no key
    if (Engine = 'groq') and (GroqKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected Groq for speech recognition but did not enter a Groq API key.'#13#10#13#10 +
        'trevo will not be able to transcribe speech without it.'#13#10 +
        'Continue anyway? (You can add the key later in Settings.)',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end
    else if (Engine = 'deepgram') and (DeepgramKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected Deepgram for speech recognition but did not enter a Deepgram API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end
    else if (Engine = 'openai') and (OpenAIKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected OpenAI for speech recognition but did not enter an OpenAI API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end;

    // Check polishing provider key
    if Result and (Provider = 'groq') and (GroqKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected Groq for text polishing but did not enter a Groq API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end
    else if Result and (Provider = 'gemini') and (GeminiKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected Gemini for text polishing but did not enter a Gemini API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end
    else if Result and (Provider = 'openai') and (OpenAIKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected OpenAI for text polishing but did not enter an OpenAI API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end
    else if Result and (Provider = 'anthropic') and (AnthropicKeyEdit.Text = '') then
    begin
      if MsgBox(
        'You selected Anthropic for text polishing but did not enter an Anthropic API key.'#13#10#13#10 +
        'Continue anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end;
  end;
end;

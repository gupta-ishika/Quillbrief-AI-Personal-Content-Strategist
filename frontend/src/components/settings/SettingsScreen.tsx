import React, { useState, useEffect } from 'react';
import {
  Save,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { SettingsResponse, TonePreset } from '../../types';
import { Button } from '../common/Button';
import { Card } from '../common/Card';

export const SettingsScreen: React.FC = () => {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [niche, setNiche] = useState<string>('');
  const [tonePreset, setTonePreset] = useState<TonePreset | ''>('');
  const [toneInstructions, setToneInstructions] = useState<string>('');
  const [timeZone, setTimeZone] = useState<string>('Asia/Kolkata');
  const [briefDay, setBriefDay] = useState<string>('mon');
  const [briefTime, setBriefTime] = useState<string>('08:00');

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getSettings();
      setSettings(data);
      if (data.niche) setNiche(data.niche);
      if (data.tone_preset) setTonePreset(data.tone_preset);
      if (data.tone_instructions) setToneInstructions(data.tone_instructions);
      if (data.time_zone) setTimeZone(data.time_zone);
      if (data.brief_day) setBriefDay(data.brief_day);
      if (data.brief_time) setBriefTime(data.brief_time);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load settings.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaveSuccess(false);
    try {
      const updated = await apiClient.updateSettings({
        niche: niche.trim(),
        tone_preset: (tonePreset as TonePreset) || undefined,
        tone_instructions: toneInstructions.trim(),
        time_zone: timeZone.trim(),
        brief_day: briefDay.trim().toLowerCase(),
        brief_time: briefTime.trim(),
      });
      setSettings(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save settings.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="py-16 flex flex-col items-center justify-center text-[#64748B]">
        <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
        <p className="text-sm">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-[#E2E8F0]">
        <div>
          <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
            Settings & Preferences
          </h1>
          <p className="text-sm text-[#64748B] mt-1">
            Manage creator profile, weekly schedule, and credentials.
          </p>
        </div>
        <Button
          onClick={handleSave}
          isLoading={saving}
          leftIcon={<Save className="w-4 h-4" />}
        >
          Save Changes
        </Button>
      </div>

      {saveSuccess && (
        <div className="p-3.5 rounded-xl bg-green-50 border border-green-200 text-xs text-[#16A34A] flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>Settings saved successfully.</span>
        </div>
      )}

      {error && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs text-[#DC2626] flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Creator Profile */}
        <Card className="p-6 space-y-4">
          <h2 className="text-base font-semibold text-[#0F172A] border-b border-[#E2E8F0] pb-2">
            Creator Profile
          </h2>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Niche (max 200 chars)
            </label>
            <input
              type="text"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              maxLength={200}
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <span className="text-[11px] text-[#64748B] mt-1 block">
              {niche.length}/200
            </span>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Tone Preset
            </label>
            <select
              value={tonePreset}
              onChange={(e) => setTonePreset(e.target.value as TonePreset)}
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select tone...</option>
              <option value="professional">Professional</option>
              <option value="friendly">Friendly</option>
              <option value="educational">Educational</option>
              <option value="conversational">Conversational</option>
              <option value="humorous">Humorous</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Additional Tone Instructions (max 500 chars)
            </label>
            <textarea
              rows={3}
              value={toneInstructions}
              onChange={(e) => setToneInstructions(e.target.value)}
              maxLength={500}
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <span className="text-[11px] text-[#64748B] mt-1 block">
              {toneInstructions.length}/500
            </span>
          </div>
        </Card>

        {/* Schedule & Timing */}
        <Card className="p-6 space-y-4">
          <h2 className="text-base font-semibold text-[#0F172A] border-b border-[#E2E8F0] pb-2">
            Weekly Brief Schedule
          </h2>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Brief Delivery Day
            </label>
            <select
              value={briefDay}
              onChange={(e) => setBriefDay(e.target.value)}
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500 capitalize"
            >
              {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((day) => (
                <option key={day} value={day}>
                  {day.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Brief Time (HH:MM)
            </label>
            <input
              type="text"
              value={briefTime}
              onChange={(e) => setBriefTime(e.target.value)}
              placeholder="08:00"
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-1.5">
              Time Zone (IANA)
            </label>
            <input
              type="text"
              value={timeZone}
              onChange={(e) => setTimeZone(e.target.value)}
              placeholder="Asia/Kolkata"
              className="w-full px-3 py-2 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {settings?.next_brief_at && (
            <div className="p-3 bg-slate-50 rounded-lg text-xs text-[#64748B]">
              Next scheduled brief:{' '}
              <span className="font-semibold text-[#0F172A]">
                {settings.next_brief_at}
              </span>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

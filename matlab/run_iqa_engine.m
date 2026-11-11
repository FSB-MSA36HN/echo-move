% RUN_IQA_ENGINE  ECHO MOVE v20.0 — offline image-quality analysis of a video.
%
%   Metrics (see docs/ALGORITHMS.md):
%     Blur      Pech-Pacheco et al., 2000     Noise     Immerkaer, 1996
%     Contrast  Peli, 1990                    PIQE      Venkatanath et al., 2015
%     Exposure  ISO 18434-1
%
%   Outputs (in cfg.outputDir): <video>_iqa.json, <video>_iqa.csv, <video>_report.png
%   The Python backend watches the JSON files (MATLAB bridge).
%
%   Author: <Họ tên> — <MSSV>       (điền thông tin sinh viên)

clear; clc; close all;
addpath(fileparts(mfilename('fullpath')));
cfg = config();
% cfg.demoMode = true;    % uncomment to run without a video file

if ~exist(cfg.outputDir, 'dir'), mkdir(cfg.outputDir); end
fprintf('Output: %s | PIQE_MODE=%s (full every %d frames)\n', ...
        cfg.outputDir, cfg.piqeMode, cfg.piqeSampleN);

%% Video source
reader = [];
if ~cfg.demoMode
    [fileName, folder] = uigetfile({'*.mp4;*.avi;*.mov', 'Video'}, 'Chọn video');
    if isequal(fileName, 0)
        warning('No video selected — falling back to demo mode.');
        cfg.demoMode = true;
    else
        reader = VideoReader(fullfile(folder, fileName));
        nFrames = floor(reader.Duration * reader.FrameRate);
        fps = reader.FrameRate;
        baseName = regexprep(fileName, '\.[^.]+$', '');
    end
end
if cfg.demoMode
    nFrames = cfg.demoFrames; fps = 30;
    fileName = 'demo_synthetic'; baseName = 'demo_synthetic';
end
fprintf('%s | %d frames | %.1f FPS\n', fileName, nFrames, fps);

hasIPT = license('test', 'Image_Toolbox');
hasWT  = license('test', 'Wavelet_Toolbox');
if ~hasIPT, warning('Image Processing Toolbox missing — using fallbacks.'); end

%% Figure
fig = figure('Name', 'ECHO MOVE v20.0', 'Position', [30 30 1500 850], 'Color', [0.05 0.08 0.12]);
titles = {'Gốc','Canny','Laplacian','Noise','Histogram','HE','Timeline','Otsu','PIQE cmp'};
ax = gobjects(1, 9);
for i = 1:9
    ax(i) = subplot(3, 3, i);
    title(ax(i), titles{i}, 'Color', 'w');
    set(ax(i), 'Color', [0.02 0.04 0.08], 'XColor', 'w', 'YColor', 'w');
end

%% Preallocated buffers
names = {'t','piqeFast','piqeFull','blur','contrast','noise','exposure','overall', ...
         'timeFast','timeFull','frameMs'};
B = struct();
for k = 1:numel(names), B.(names{k}) = zeros(1, nFrames); end

%% Main loop
idx = 0; tTotal = tic;
while idx < nFrames
    tFrame = tic;
    if cfg.demoMode
        frame = iqa.syntheticFrame(idx + 1, cfg.frameSize);
    else
        if ~hasFrame(reader), break; end
        frame = readFrame(reader);
        if hasIPT
            frame = imresize(frame, cfg.frameSize);
        else
            frame = frame(1:4:end, 1:4:end, :);
        end
    end
    idx = idx + 1;
    B.t(idx) = (idx - 1) / fps;

    if hasIPT, gray = im2double(rgb2gray(frame)); else, gray = iqa.toGray(frame); end

    tt = tic; piqeFast = iqa.mscnQuality(gray); B.timeFast(idx) = toc(tt) * 1000;
    wantFull = any(strcmp(cfg.piqeMode, {'full','both'})) && mod(idx, cfg.piqeSampleN) == 0;
    if wantFull
        tt = tic; piqeFull = iqa.piqeFull(gray); B.timeFull(idx) = toc(tt) * 1000;
    elseif idx > 1
        piqeFull = B.piqeFull(idx - 1);
    else
        piqeFull = piqeFast;
    end
    piqeScore = piqeFast;
    if strcmp(cfg.piqeMode, 'full'), piqeScore = piqeFull; end

    B.piqeFast(idx) = piqeFast;  B.piqeFull(idx) = piqeFull;
    B.blur(idx)     = iqa.blurScore(gray);
    B.contrast(idx) = iqa.contrastScore(gray);
    B.noise(idx)    = iqa.noiseScore(gray);
    B.exposure(idx) = iqa.exposureScore(gray);
    B.overall(idx)  = iqa.overall(piqeScore, B.blur(idx), B.contrast(idx), ...
                                  B.noise(idx), B.exposure(idx), cfg.weights);
    B.frameMs(idx)  = toc(tFrame) * 1000;

    if mod(idx, cfg.plotEveryN) == 0 || idx == nFrames
        updatePlots(ax, frame, gray, B, idx, cfg, hasIPT, hasWT);
        if cfg.streamJson && mod(idx, cfg.streamEveryN) == 0 && idx < nFrames
            writeJson(cfg, baseName, buildSummary(B, idx, fileName, fps, cfg, 'ANALYZING', tTotal), []);
        end
    end
end

%% Summary & export
status = classify(mean(B.overall(1:idx)), cfg.thresholds);
summary = buildSummary(B, idx, fileName, fps, cfg, status, tTotal);
perFrame = arrayfun(@(i) struct('t', B.t(i), 'piqe', B.piqeFast(i), 'piqe_full', B.piqeFull(i), ...
    'blur', B.blur(i), 'contrast', B.contrast(i), 'noise', B.noise(i), ...
    'exposure', B.exposure(i), 'overall', B.overall(i), 'time_ms', B.frameMs(i)), 1:idx);
writeJson(cfg, baseName, summary, perFrame);

T = table(B.t(1:idx)', B.piqeFast(1:idx)', B.piqeFull(1:idx)', B.blur(1:idx)', ...
    B.contrast(1:idx)', B.noise(1:idx)', B.exposure(1:idx)', B.overall(1:idx)', B.frameMs(1:idx)', ...
    'VariableNames', {'Time_s','PIQE_Fast','PIQE_Full','Blur','Contrast','Noise','Exposure','Overall','FrameTime_ms'});
writetable(T, fullfile(cfg.outputDir, [baseName '_iqa.csv']));
try
    exportgraphics(fig, fullfile(cfg.outputDir, [baseName '_report.png']), 'Resolution', 150);
catch err
    warning('Could not export report image: %s', err.message);
end

fprintf('\n=== RESULT: %d frames, %.2fs, %.1f FPS ===\n', idx, summary.total_seconds, summary.effective_fps);
fprintf(' PIQE fast %.1f | full %.1f | corr %.3f\n', summary.piqe, summary.piqe_full, summary.piqe_correlation);
fprintf(' Blur %.1f  Contrast %.1f  Noise %.1f  Exposure %.1f\n', ...
        summary.blur, summary.contrast, summary.noise, summary.exposure);
fprintf(' OVERALL %.1f (%s)\n', summary.overall, status);

%% ---------------------------------------------------------------- helpers
function status = classify(score, th)
if score >= th.safe, status = 'SAFE';
elseif score >= th.warning, status = 'WARNING';
else, status = 'DANGER'; end
end

function s = buildSummary(B, n, video, fps, cfg, status, tTotal)
r = 0;
if n > 10
    c = corrcoef(B.piqeFull(1:n), B.piqeFast(1:n));   % no Statistics Toolbox needed
    r = c(1, 2);
end
fullT = B.timeFull(B.timeFull > 0);
if isempty(fullT), fullT = 0; end
colors = struct('SAFE', [0.14 0.50 0.32], 'WARNING', [0.98 0.66 0], 'DANGER', [0.61 0.14 0.14], ...
                'ANALYZING', [0.98 0.66 0]);
s = struct('video', video, 'frames', n, 'fps', fps, ...
    'piqe', mean(B.piqeFast(1:n)), 'piqe_full', mean(B.piqeFull(1:n)), ...
    'blur', mean(B.blur(1:n)), 'contrast', mean(B.contrast(1:n)), 'noise', mean(B.noise(1:n)), ...
    'exposure', mean(B.exposure(1:n)), 'overall', mean(B.overall(1:n)), ...
    'time_fast_ms', mean(B.timeFast(1:n)), 'time_full_ms', mean(fullT), ...
    'avg_frame_ms', mean(B.frameMs(1:n)), 'effective_fps', 1000 / mean(B.frameMs(1:n)), ...
    'piqe_correlation', r, 'total_seconds', toc(tTotal), ...
    'status', status, 'color', colors.(status), 'demo_mode', cfg.demoMode, ...
    'piqe_mode', cfg.piqeMode, 'progress', n / numel(B.t), 'version', cfg.version, ...
    'updated_at', datestr(now, 'yyyy-mm-dd HH:MM:SS'));
end

function writeJson(cfg, baseName, summary, perFrame)
out = struct('summary', summary, 'per_frame', perFrame);
path = fullfile(cfg.outputDir, [baseName '_iqa.json']);
tmp = [path '.tmp'];
fid = fopen(tmp, 'w');
if fid < 0, warning('Cannot write %s', tmp); return; end
fprintf(fid, '%s', jsonencode(out, 'PrettyPrint', true));
fclose(fid);
movefile(tmp, path, 'f');   % atomic-ish replace so the Python bridge never sees half a file
end

function updatePlots(ax, frame, gray, B, idx, cfg, hasIPT, hasWT)
dark = {'Color', [0.02 0.04 0.08], 'XColor', 'w', 'YColor', 'w'};
t = B.t(1:idx);
imshow(frame, 'Parent', ax(1));
if hasIPT, imshow(edge(gray, 'Canny'), 'Parent', ax(2)); else
    [gx, gy] = gradient(gray); imshow(sqrt(gx.^2 + gy.^2) > 0.1, 'Parent', ax(2)); end
lap = abs(gray - iqa.gaussian(gray, 1));
imshow(mat2gray(lap), 'Parent', ax(3));
if hasWT
    [c, ~] = wavedec2(gray, 1, 'db1'); sz = floor(size(gray) / 2);
    detail = reshape(c(end-3*prod(sz)+1:end-2*prod(sz)), sz);
    imshow(mat2gray(abs(detail)), 'Parent', ax(4));
else
    imshow(mat2gray(lap), 'Parent', ax(4));
end
cla(ax(5)); histogram(ax(5), gray(:), 50, 'FaceColor', [0 1 0.8]); set(ax(5), dark{:});
if hasIPT, imshow(histeq(gray), 'Parent', ax(6)); else, imshow(gray, 'Parent', ax(6)); end
cla(ax(7)); hold(ax(7), 'on'); grid(ax(7), 'on');
plot(ax(7), t, B.blur(1:idx), 'g-', t, B.noise(1:idx), 'b-', t, B.contrast(1:idx), 'r-', ...
     t, B.overall(1:idx), 'y-', 'LineWidth', 1.5);
legend(ax(7), {'Blur','Noise','Contrast','Overall'}, 'TextColor', 'w', 'Location', 'southwest');
set(ax(7), dark{:});
if hasIPT, lvl = graythresh(gray); imshow(imbinarize(gray, lvl), 'Parent', ax(8));
else, lvl = mean(gray(:)); imshow(gray > lvl, 'Parent', ax(8)); end
title(ax(8), sprintf('Otsu %.2f', lvl), 'Color', 'w');
cla(ax(9)); hold(ax(9), 'on'); grid(ax(9), 'on');
if strcmp(cfg.piqeMode, 'both')
    plot(ax(9), t, B.piqeFull(1:idx), 'r-', t, B.piqeFast(1:idx), 'g--', 'LineWidth', 2);
    legend(ax(9), {'Full','Fast'}, 'TextColor', 'w', 'Location', 'southwest');
    if idx > 10
        cc = corrcoef(B.piqeFull(1:idx), B.piqeFast(1:idx));
        title(ax(9), sprintf('PIQE (r=%.3f)', cc(1, 2)), 'Color', 'w');
    end
end
set(ax(9), dark{:});
drawnow limitrate;
end

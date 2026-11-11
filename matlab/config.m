function cfg = config()
%CONFIG Central settings for the ECHO MOVE IQA engine.
%   Override any field before calling run_iqa_engine, e.g.
%       cfg = config(); cfg.demoMode = true;

cfg.demoMode      = false;          % true: synthetic frames, no video needed
cfg.demoFrames    = 150;
cfg.piqeMode      = 'both';         % 'fast' | 'full' | 'both'
cfg.piqeSampleN   = 30;             % compute block PIQE every N frames
cfg.weights       = [0.25 0.25 0.20 0.15 0.15];  % piqe blur contrast noise exposure
cfg.frameSize     = [240 320];
cfg.streamJson    = true;           % write partial JSON while processing
cfg.streamEveryN  = 10;
cfg.plotEveryN    = 5;
cfg.thresholds    = struct('safe', 80, 'warning', 60);
cfg.outputDir     = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'output');
cfg.version       = '20.0';
end

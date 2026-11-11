function s = mscnQuality(gray)
%MSCNQUALITY Fast quality proxy (0-100): 100 - 100*std(MSCN). Not the full PIQE.
s = max(100 - std(iqa.mscn(gray), 0, 'all') * 100, 0);
end

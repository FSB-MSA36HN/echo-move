function g = toGray(frame)
%TOGRAY RGB uint8 frame -> double gray in [0,1].
g = (0.299*double(frame(:,:,1)) + 0.587*double(frame(:,:,2)) + 0.114*double(frame(:,:,3))) / 255;
end

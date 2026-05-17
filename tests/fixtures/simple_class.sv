class MyDriver;
    logic [7:0] data;
    function void drive(logic [7:0] d);
        data = d;
    endfunction
endclass

module top;
    MyDriver drv;
    logic [7:0] val;
    initial begin
        drv = new();
        drv.drive(val);
    end
endmodule
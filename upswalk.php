<?php

$topic_base = file_get_contents("MQTT_BASE_TOPIC");

$ups = array("172.22.62.50","172.22.62.51");

$oids = array("InputLineVoltage"=>"iso.3.6.1.2.1.33.1.3.3.1.3.1",
              "BatteryCapacity"=>"iso.3.6.1.2.1.33.1.2.4.0",
              "BatteryTemperature"=>"iso.3.6.1.2.1.33.1.2.7.0",
              "UPSload"=>"iso.3.6.1.2.1.33.1.4.4.1.5.1",
              "OutputVoltage"=>"iso.3.6.1.2.1.33.1.9.3.0"
);



$i=1;
foreach($ups as $ups_){
foreach($oids as $key => $oids_){


    #$value = shell_exec("snmpwalk -c public -v 2c ".$ups_." -m '' ".$oids_." -Ov | grep -o '[0-9]*'");
    
    # -Oqv = value only
    # -r1  = retry 1
    # -t1  = timeout 1 sec
    $value = shell_exec("snmpget -c public -v 2c -Oqv -r1 -t1 ".$ups_." -m '' ".$oids_);
     
    $data = "ups/".$i."/".$key." ".$value."\n";

    echo trim($topic_base)."/".str_replace("\n","",$data)."\n";

}               
$i++;
}
                    
?>
